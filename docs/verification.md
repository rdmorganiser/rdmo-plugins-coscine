# Signing and verification

This document describes the technical format and verification procedure used by `rdmo-plugins-coscine`.

It is primarily intended for Coscine integration developers, RDMO plugin maintainers, and administrators debugging signature or payload verification problems.

For installation and normal use of the plugin, see the main [README](../README.md).

## Export structure

The exported file has the following structure:

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

- `version`: version of the export format
- `import_type`: fixed value identifying the payload as an RDMO import payload
- `catalog_title`: title of the RDMO catalogue used by the project
- `catalog_uri`: URI of the RDMO catalogue used by the project
- `project_id`: RDMO project ID as a string
- `data`: exported answers
- `data[].attribute_uri`: RDMO domain attribute URI for the exported value
- `data[].question`: question text
- `data[].set`: rendered set label for repeated or structured values
- `data[].values`: rendered answer value or values
- `jwt`: signed JWT created with the shared secret

## What the JWT signs

The JWT does not sign the complete exported JSON object directly.

Instead, it contains a SHA-256 hash of the canonicalized unsigned payload. The unsigned payload is the complete export object without the `jwt` field:

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
2. the JSON payload has not been changed after export

## Payload canonicalization

The importing service must calculate the payload hash using the same JSON canonicalization as the exporter.

The relevant Python `json.dumps` settings are:

```python
json.dumps(
    payload,
    ensure_ascii=False,
    separators=(',', ':'),
    sort_keys=True,
)
```

The equivalent settings are therefore:

- `sort_keys=True`
- `separators=(',', ':')`
- `ensure_ascii=False`

The canonicalization must match on both sides before calculating the SHA-256 hash.

## Verification with Python

The importing side should verify both the JWT signature and the payload hash.

Install `PyJWT` first. The package is named `PyJWT`, but imported as `jwt` in Python. Do not install the package named `jwt`.

Set the shared secret in the shell:

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
        separators=(',', ':'),
        sort_keys=True,
    )


def get_unsigned_payload(export_data: dict) -> dict:
    return {
        key: value
        for key, value in export_data.items()
        if key != 'jwt'
    }


def verify_rdmo_coscine_export(
    export_data: dict,
    shared_secret: str,
) -> dict:
    token = export_data['jwt']
    payload = get_unsigned_payload(export_data)

    claims = jwt.decode(
        token,
        shared_secret,
        algorithms=['HS256', 'HS384', 'HS512'],
    )

    canonical_payload = canonicalize_payload(payload).encode('utf-8')
    expected_hash = hashlib.sha256(canonical_payload).hexdigest()

    if claims['project_id'] != payload['project_id']:
        raise ValueError(
            'JWT project_id does not match payload project_id'
        )

    if claims['payload_sha256'] != expected_hash:
        raise ValueError(
            'JWT payload hash does not match JSON payload'
        )

    return claims


def get_shared_secret() -> str:
    shared_secret = os.getenv('SHARED_SECRET')

    if shared_secret:
        return shared_secret

    raise RuntimeError('SHARED_SECRET is not set')


export_data = json.loads(
    Path('rdmo-coscine-export.json').read_text(encoding='utf-8')
)

claims = verify_rdmo_coscine_export(
    export_data,
    get_shared_secret(),
)

print('JWT signature and payload hash are valid', claims)
```

## Working with exported JSON in a Python REPL

When pasting exported JSON into a Python REPL, use a raw string.

Otherwise Python can consume JSON escape sequences before `json.loads()` sees them. For example:

```python
import json

data_text = r'''{
  "version": "1.0.0",
  "set": "Set \"Dataset 1\""
}'''

export_data = json.loads(data_text)
```

## Troubleshooting the shared secret

To check that the environment variable contains exactly what you expect:

```python
shared_secret = os.getenv('SHARED_SECRET')

print(repr(shared_secret))
print(len(shared_secret or ''))
```

An error such as:

```text
jwt.exceptions.InvalidSignatureError: Signature verification failed
```

means that the JWT is structurally valid but its signature could not be verified using the supplied secret.

Check that:

- `SHARED_SECRET` has exactly the same value as `COSCINE_EXPORTS['jwt_secret']`
- the variable is exported in the same shell from which Python is started
- the value does not contain accidental quotes
- the value does not contain additional whitespace or a trailing newline

## Checking the payload hash without verifying the signature

For debugging purposes, the JWT can be decoded without signature verification so that the embedded payload hash can be compared with the exported JSON:

```python
claims = jwt.decode(
    export_data['jwt'],
    options={'verify_signature': False},
)

payload = get_unsigned_payload(export_data)

expected_hash = hashlib.sha256(
    canonicalize_payload(payload).encode('utf-8')
).hexdigest()

print(claims['payload_sha256'] == expected_hash)
```

This only checks whether the hash stored in the JWT matches the JSON payload. It does **not** authenticate the JWT and must not be used as a replacement for signature verification.

## Verification in the browser console

The exported JSON can also be inspected and verified in a browser.

The following example works with Firefox JSON Viewer variables when available. In other browsers, either run it on a page displaying the raw JSON or paste the exported JSON into `EXPORTED_JSON` or `EXPORTED_JSON_TEXT`.

Replace `SHARED_SECRET` with the configured `COSCINE_EXPORTS['jwt_secret']`.

The browser must provide `crypto.subtle`, which is normally available in secure contexts such as HTTPS pages and localhost.

```js
const SHARED_SECRET = "change-me-to-the-configured-shared-secret";

// Optional fallback:
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
    "Could not find exported JSON. " +
    "Paste it into EXPORTED_JSON or EXPORTED_JSON_TEXT.",
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

  return Uint8Array.from(
    binary,
    (char) => char.charCodeAt(0),
  );
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
  const hashArray = Array.from(
    new Uint8Array(hashBuffer),
  );

  return hashArray
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function verifyRdmoCoscineExport(
  exportData,
  sharedSecret,
) {
  const { jwt, ...unsignedPayload } = exportData;

  const claims = await verifyJwtSignature(
    jwt,
    sharedSecret,
  );

  const canonicalPayload = canonicalize(unsignedPayload);
  const expectedHash = await sha256Hex(canonicalPayload);

  if (claims.project_id !== unsignedPayload.project_id) {
    throw new Error(
      "JWT project_id does not match payload project_id",
    );
  }

  if (claims.payload_sha256 !== expectedHash) {
    throw new Error(
      "JWT payload hash does not match JSON payload",
    );
  }

  return claims;
}

const exportData = readExportData();

const claims = await verifyRdmoCoscineExport(
  exportData,
  SHARED_SECRET,
);

console.log(
  "JWT signature and payload hash are valid",
  claims,
);
```

If verification succeeds, the console prints the JWT claims. If either the JSON payload or JWT signature has been changed, verification fails.

## Verification with Node.js and `jose`

For production integrations, verify both the JWT signature and payload hash.

The following example uses Node.js and [`jose`](https://github.com/panva/jose):

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
  return createHash("sha256")
    .update(input, "utf8")
    .digest("hex");
}

export async function verifyRdmoCoscineExport(
  exportData,
  sharedSecret,
) {
  const { jwt: token, ...unsignedPayload } = exportData;
  const secretKey = new TextEncoder().encode(sharedSecret);

  const { payload: claims } = await jwtVerify(
    token,
    secretKey,
    {
      algorithms: ["HS256"],
    },
  );

  const canonicalPayload = canonicalize(unsignedPayload);
  const expectedHash = sha256Hex(canonicalPayload);

  if (claims.project_id !== unsignedPayload.project_id) {
    throw new Error(
      "JWT project_id does not match payload project_id",
    );
  }

  if (claims.payload_sha256 !== expectedHash) {
    throw new Error(
      "JWT payload hash does not match JSON payload",
    );
  }

  return claims;
}
```

For production code, configure the accepted algorithm to match the algorithm configured by the RDMO instance and do not disable JWT signature verification.