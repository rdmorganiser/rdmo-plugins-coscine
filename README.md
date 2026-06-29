rdmo-plugins-coscine
==================
This project export plugin provides a signed JSON export intended for import into Coscine.

The export contains a RDMO payload plus a signed JWT. The JWT contains a SHA-256 hash of the unsigned payload.
This allows an importing service to verify that the JSON payload was not changed after export.

Setup
-----

Install the plugin in your RDMO virtual environment using pip (directly from GitHub):

```bash
pip install git+https://github.com/rdmorganiser/rdmo-plugins-coscine
```

Add the `rdmo_coscine` app to `INSTALLED_APPS` and the plugin to `PROJECT_EXPORTS` in `config/settings/local.py`:

```python
INSTALLED_APPS += ['rdmo_coscine']

...

PROJECT_EXPORTS += [
    ("coscine-json", _("Export to Coscine"), "rdmo_coscine.exports.CoscineJSONExport"),
]
```

Configure the shared JWT secret, this needs to be shared with the Coscine instance.

```python
COSCINE_EXPORTS = {
    "jwt_secret": "change-me-to-a-long-random-shared-secret-of-at-least-32-characters-length",
    "jwt_algorithm": "HS256",
    "jwt_issuer": "rdmo",
}
```

`jwt_secret` must be the same secret that the importing service uses to verify the
JWT signature. Use a long random value and keep it private.

Supported JWT algorithms are:

- `HS256`
- `HS384`
- `HS512`

`HS256` is the default and recommended value unless there is a specific reason to
use another HMAC algorithm.

Additional infos about the export shape and the signing and verification
-----

The exported file has this shape:

```json
{
  "version": "1.0.0",
  "import_type": "rdmo",
  "catalog_title": "Example catalog",
  "catalog_uri": "https://example.org/terms/catalog/example",
  "project_id": "123",
  "data": [
    {
      "attribute_uri": "https://example.org/terms/domain/project/title",
      "question": "Project title",
      "set": "",
      "values": "Example project"
    }
  ],
  "jwt": "eyJ..."
}
```

### Payload fields

- `version`: version of this export format
- `import_type`: fixed value identifying the payload as an RDMO import payload
- `catalog_title`: title of the RDMO catalog used by the project
- `catalog_uri`: URI of the RDMO catalog used by the project
- `project_id`: the RDMO project id as string
- `data`: the exported answers
- `data[].attribute_uri`: the RDMO domain attribute URI for the exported value
- `data[].question`: the question text
- `data[].set`: the rendered set label for repeated/structured values
- `data[].values`: the rendered answer value or values
- `jwt`: a signed JWT created with the shared secret

### What the JWT signs

The JWT does not sign the complete exported JSON object. It signs a SHA-256 hash
of the unsigned payload. In the exported JSON, the unsigned payload is the full
object without the `jwt` field:

```json
{
  "version": "1.0.0",
  "import_type": "rdmo",
  "catalog_title": "Example catalog",
  "catalog_uri": "https://example.org/terms/catalog/example",
  "project_id": "123",
  "data": []
}
```

The JWT claims currently contain:

- `project_id`
- `payload_sha256`
- `iat`
- optionally `iss`

This allows the importing service to verify two things:

1. the JWT was created by a party holding the shared secret
2. the JSON payload was not changed after export

The canonicalization settings must match exactly on both sides:

- `sort_keys=True`
- `separators=(",", ":")`
- `ensure_ascii=False`

### Verification example: Python

The importing side should verify both the JWT signature and the payload hash.
Install `PyJWT` first. The package name is `PyJWT`, but it is imported as
`jwt` in Python. Do not install the package named `jwt`.

Set the shared secret in the same shell before starting Python:

```bash
export SHARED_SECRET='change-me-to-the-configured-shared-secret'
```

Start Python with `PyJWT` available:

```bash
uv run --with PyJWT python
```

For an interactive `bpython` session:

```bash
uv run --with bpython --with PyJWT bpython
```

Then load and verify the exported file:

```python
import hashlib
import json
import os
from pathlib import Path

import jwt


def canonicalize_payload(payload: dict) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def get_unsigned_payload(export_data: dict) -> dict:
    return {
        key: value
        for key, value in export_data.items()
        if key != "jwt"
    }


def verify_rdmo_coscine_export(export_data: dict, shared_secret: str) -> dict:
    token = export_data["jwt"]
    payload = get_unsigned_payload(export_data)

    claims = jwt.decode(token, shared_secret, algorithms=["HS256", "HS384", "HS512"])

    canonical_payload = canonicalize_payload(payload).encode("utf-8")
    expected_hash = hashlib.sha256(canonical_payload).hexdigest()

    if claims["project_id"] != payload["project_id"]:
        raise ValueError("JWT project_id does not match payload project_id")

    if claims["payload_sha256"] != expected_hash:
        raise ValueError("JWT payload hash does not match JSON payload")

    return claims


def get_shared_secret() -> str:
    shared_secret = os.getenv("SHARED_SECRET")
    if shared_secret:
        return shared_secret

    raise RuntimeError("SHARED_SECRET is not set")


export_data = json.loads(Path("rdmo-coscine-export.json").read_text(encoding="utf-8"))
claims = verify_rdmo_coscine_export(export_data, get_shared_secret())
print("JWT signature and payload hash are valid", claims)
```

When pasting exported JSON into a Python REPL, use a raw string. Otherwise Python
will consume JSON escape sequences before `json.loads()` sees them. For example,
`\"` inside the JSON would become `"` inside the Python string and break values
such as `"set": "Set \"Dataset 1\""`.

```python
import json

data_text = r'''{
  "version": "1.0.0",
  "set": "Set \"Dataset 1\""
}'''

export_data = json.loads(data_text)
```

To check that the environment variable contains exactly what you expect:

```python
shared_secret = os.getenv("SHARED_SECRET")
print(repr(shared_secret))
print(len(shared_secret or ""))
```

`jwt.exceptions.InvalidSignatureError: Signature verification failed` means the
JWT is valid structurally, but the secret used for verification does not exactly
match the secret used during export. Check that `SHARED_SECRET` has the same
value as `COSCINE_EXPORTS["jwt_secret"]`, that it is exported in the same shell
where Python is started, and that it does not contain accidental quotes,
whitespace, or a trailing newline.

If signature verification fails but you want to check whether the copied or
downloaded JSON payload is intact, decode the JWT without verifying the signature
and compare the payload hash:

```python
claims = jwt.decode(export_data["jwt"], options={"verify_signature": False})
payload = get_unsigned_payload(export_data)
expected_hash = hashlib.sha256(
    canonicalize_payload(payload).encode("utf-8")
).hexdigest()

print(claims["payload_sha256"] == expected_hash)
```

### Verification example: browser console

Open the exported JSON in a browser and open the developer console. The snippet
works with Firefox's JSON Viewer variables when they are available. In other
browsers, either run it on a page that displays only the raw JSON text, or paste
the exported JSON into `EXPORTED_JSON` or `EXPORTED_JSON_TEXT`.

Paste this snippet into the console. Replace `SHARED_SECRET` with the configured
`COSCINE_EXPORTS["jwt_secret"]`. The browser needs access to `crypto.subtle`,
which is available on HTTPS pages and localhost.

```js
const SHARED_SECRET = "change-me-to-the-configured-shared-secret";

// Optional fallback for browsers that do not expose JSON Viewer variables:
// const EXPORTED_JSON = { "version": "1.0.0", "...": "..." };
// const EXPORTED_JSON_TEXT = `{ "version": "1.0.0", "...": "..." }`;

function readExportData() {
  if (typeof EXPORTED_JSON !== "undefined") {
    return EXPORTED_JSON;
  }

  if (typeof EXPORTED_JSON_TEXT !== "undefined") {
    return JSON.parse(EXPORTED_JSON_TEXT);
  }

  if (globalThis.$json?.data) {
    return globalThis.$json.data;
  }

  if (globalThis.$json?.text) {
    return JSON.parse(globalThis.$json.text);
  }

  const bodyText = document.body?.innerText?.trim();
  if (bodyText?.startsWith("{")) {
    return JSON.parse(bodyText);
  }

  throw new Error(
    "Could not find exported JSON. Paste it into EXPORTED_JSON or EXPORTED_JSON_TEXT.",
  );
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(",")}]`;
  }

  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();

    return `{${keys
      .map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`)
      .join(",")}}`;
  }

  return JSON.stringify(value);
}

function base64UrlToBytes(input) {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(
    base64.length + ((4 - (base64.length % 4)) % 4),
    "=",
  );
  const binary = atob(padded);

  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function base64UrlDecodeJson(input) {
  const bytes = base64UrlToBytes(input);
  const json = new TextDecoder().decode(bytes);

  return JSON.parse(json);
}

function bytesEqual(left, right) {
  if (left.length !== right.length) {
    return false;
  }

  let diff = 0;
  for (let index = 0; index < left.length; index += 1) {
    diff |= left[index] ^ right[index];
  }

  return diff === 0;
}

async function verifyJwtSignature(token, sharedSecret) {
  const parts = token.split(".");

  if (parts.length !== 3) {
    throw new Error("Invalid JWT format");
  }

  const header = base64UrlDecodeJson(parts[0]);
  const hashByAlgorithm = {
    HS256: "SHA-256",
    HS384: "SHA-384",
    HS512: "SHA-512",
  };
  const hash = hashByAlgorithm[header.alg];

  if (!hash) {
    throw new Error(`Unsupported JWT algorithm: ${header.alg}`);
  }

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(sharedSecret),
    { name: "HMAC", hash },
    false,
    ["sign"],
  );
  const signedContent = `${parts[0]}.${parts[1]}`;
  const expectedSignature = new Uint8Array(
    await crypto.subtle.sign(
      "HMAC",
      key,
      new TextEncoder().encode(signedContent),
    ),
  );
  const actualSignature = base64UrlToBytes(parts[2]);

  if (!bytesEqual(actualSignature, expectedSignature)) {
    throw new Error("JWT signature is invalid");
  }

  return base64UrlDecodeJson(parts[1]);
}

async function sha256Hex(input) {
  const data = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));

  return hashArray
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function verifyRdmoCoscineExport(exportData, sharedSecret) {
  const { jwt, ...unsignedPayload } = exportData;
  const claims = await verifyJwtSignature(jwt, sharedSecret);

  const canonicalPayload = canonicalize(unsignedPayload);
  const expectedHash = await sha256Hex(canonicalPayload);

  if (claims.project_id !== unsignedPayload.project_id) {
    throw new Error("JWT project_id does not match payload project_id");
  }

  if (claims.payload_sha256 !== expectedHash) {
    throw new Error("JWT payload hash does not match JSON payload");
  }

  return claims;
}

const exportData = readExportData();
const claims = await verifyRdmoCoscineExport(exportData, SHARED_SECRET);
console.log("JWT signature and payload hash are valid", claims);
```

If verification succeeds, the console prints the JWT claims. If the JSON payload
or JWT signature was changed, the snippet throws an error.

### Verification example: JavaScript with full JWT verification

For production imports, verify both the JWT signature and the payload hash. This
example uses Node.js and `jose`:

```js
import { createHash } from "crypto";
import { jwtVerify } from "jose";

function canonicalize(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalize).join(",")}]`;
  }

  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();

    return `{${keys
      .map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`)
      .join(",")}}`;
  }

  return JSON.stringify(value);
}

function sha256Hex(input) {
  return createHash("sha256").update(input, "utf8").digest("hex");
}

export async function verifyRdmoCoscineExport(exportData, sharedSecret) {
  const { jwt: token, ...unsignedPayload } = exportData;
  const secretKey = new TextEncoder().encode(sharedSecret);

  const { payload: claims } = await jwtVerify(token, secretKey, {
    algorithms: ["HS256"],
  });

  const canonicalPayload = canonicalize(unsignedPayload);
  const expectedHash = sha256Hex(canonicalPayload);

  if (claims.project_id !== unsignedPayload.project_id) {
    throw new Error("JWT project_id does not match payload project_id");
  }

  if (claims.payload_sha256 !== expectedHash) {
    throw new Error("JWT payload hash does not match JSON payload");
  }

  return claims;
}
```

Acknowledgements
-----
This plugin has been developed through the [DMP4NFDI](https://dmp.services.base4nfdi.de/) project, 
as an Incubator with [Coscine](https://about.coscine.de/en/) for the RDMO client of the [NFDI4ING](https://www.nfdi4ing.de/) consortium.

DMP4NFDI is a Basic Service of Base4NFDI, funded by the German Research Foundation (DFG)
under project [521453681](https://gepris.dfg.de/gepris/projekt/521453681). NFDI4ING is funded by the DFG under project [442146713](https://gepris.dfg.de/gepris/projekt/442146713). 
Both projects are part of the German National Research Data Infrastructure (NFDI).
