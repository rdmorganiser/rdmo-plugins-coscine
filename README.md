# rdmo-plugins-coscine

This project export plugin provides a signed JSON export intended for importing RDMO project metadata into [Coscine](https://www.coscine.de/).

The export contains the RDMO project metadata together with a signed JWT. The signature allows Coscine to verify 
that the export was signed using the configured shared secret and that the exported data has not been modified.

## Setup

Install the plugin in your RDMO virtual environment using pip:

```bash
pip install git+https://github.com/rdmorganiser/rdmo-plugins-coscine
```

Add the `rdmo_coscine` app to `INSTALLED_APPS` and the export plugin to `PROJECT_EXPORTS` in `config/settings/local.py`:

```python
INSTALLED_APPS += ['rdmo_coscine']

PROJECT_EXPORTS += [
    ('coscine-json', _('Export to Coscine'), 'rdmo_coscine.exports.CoscineJSONExport'),
]
```

Configure the shared JWT secret:

```python
COSCINE_EXPORTS = {
    'jwt_secret': 'change-me-to-a-long-random-shared-secret-of-at-least-32-characters-length',
    'jwt_algorithm': 'HS256',
    'jwt_issuer': 'rdmo',
}
```

The `jwt_secret` must be the same secret that the Coscine importing service uses to verify the export. Use a long random value and keep it private. By default, the export is signed using the `HS256` HMAC algorithm. 

## Further information

For instructions on importing project metadata from data management plans in RDMO into Coscine, see the [Coscine documentation](https://docs.coscine.de/de/projects/import-from-rdmo/).

For the Coscine workflow, we recommend the following RDMO option set providers for collecting identifiers and controlled vocabulary terms in a form that can be recognized during export:

- [DFG plugin](https://github.com/rdmorganiser/rdmo-plugins-dfg) for DFG subject classifications and review boards
- [ROR plugin](https://github.com/rdmorganiser/rdmo-plugins-ror) for research organisation identifiers
- [ORCID plugin](https://github.com/rdmorganiser/rdmo-plugins-orcid) for researcher identifiers

These plugins are not runtime dependencies of `rdmo-plugins-coscine` itself. Instead, they are recommended for the RDMO catalogs used in the Coscine workflow.

Their option set providers should be enabled in the RDMO instance and assigned to the appropriate option sets and questions in the relevant catalogs. This ensures that identifiers and classification values are stored in the project metadata in a form that the Coscine exporter can recognize and transform where necessary.

Installing the provider plugins alone is therefore not sufficient: the corresponding catalogue questions need to use these provider-backed option sets.

The Coscine exporter contains its own mapping data where required for export-specific transformations, for example for converting supported DFG review board values into the representation expected by Coscine.

## Export format

The plugin produces a JSON export with the following basic structure:

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

The `data` array contains the exported answers from the RDMO project. The `jwt` field contains the signature information used by the importing service to verify the export.

For recognized DFG, ROR, and ORCID identifiers, the exporter uses identifier URLs where appropriate instead of only the rendered answer text. Some export-specific transformations,
such as the mapping of DFG review board values to the representation expected by Coscine, are handled directly by this plugin using bundled mapping data.

## Signing and verification

The exported JSON includes a signed JWT containing a SHA-256 hash of the unsigned payload. This allows the importing service to verify the JWT signature and the integrity of the exported data.

Technical details about the payload format, JWT claims, canonicalization, verification implementations, and troubleshooting are documented separately in [docs/verification.md](docs/verification.md).

## Acknowledgements

This plugin has been developed through the [DMP4NFDI](https://dmp.services.base4nfdi.de/) project, 
as an Incubator with [Coscine](https://about.coscine.de/en/) for the RDMO client of the [NFDI4ING](https://www.nfdi4ing.de/) consortium.

DMP4NFDI is a Basic Service of Base4NFDI, funded by the German Research Foundation (DFG) under project [521453681](https://gepris.dfg.de/gepris/projekt/521453681). NFDI4ING is funded by the DFG under project [442146713](https://gepris.dfg.de/gepris/projekt/442146713).

Both projects are part of the German National Research Data Infrastructure (NFDI).