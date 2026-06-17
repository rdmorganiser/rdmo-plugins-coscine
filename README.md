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

```python
import hashlib
import json

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

    claims = jwt.decode(token, shared_secret, algorithms=["HS256"])

    canonical_payload = canonicalize_payload(payload).encode("utf-8")
    expected_hash = hashlib.sha256(canonical_payload).hexdigest()

    if claims["project_id"] != payload["project_id"]:
        raise ValueError("JWT project_id does not match payload project_id")

    if claims["payload_sha256"] != expected_hash:
        raise ValueError("JWT payload hash does not match JSON payload")

    return claims
```

### Verification example: vanilla browser JavaScript hash check

This example verifies the payload hash without any JavaScript dependencies. It
uses the browser's built-in `crypto.subtle.digest("SHA-256", ...)` API.

This only verifies that the JSON payload matches the `payload_sha256` claim inside
the JWT. It does not verify that the JWT was signed by a trusted party. For a
trusted import, verify the JWT signature with the shared secret as well.

```js
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

function base64UrlDecode(input) {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(
    base64.length + ((4 - (base64.length % 4)) % 4),
    "=",
  );

  return atob(padded);
}

function decodeJwtPayload(token) {
  const parts = token.split(".");

  if (parts.length !== 3) {
    throw new Error("Invalid JWT format");
  }

  return JSON.parse(base64UrlDecode(parts[1]));
}

async function sha256Hex(input) {
  const data = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));

  return hashArray
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function verifyPayloadHash(exportData) {
  const { jwt, ...unsignedPayload } = exportData;
  const claims = decodeJwtPayload(jwt);

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
```

Usage:

```js
const claims = await verifyPayloadHash(exportData);
console.log("Payload hash is valid", claims);
```

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