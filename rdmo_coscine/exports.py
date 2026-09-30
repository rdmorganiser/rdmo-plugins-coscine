import hashlib
import json
import re
import time
from functools import lru_cache
from typing import Any
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse

import jwt

from rdmo.core.utils import render_to_json
from rdmo.projects.exports import AnswersExportMixin, Export
from rdmo.views.templatetags import view_tags
from rdmo.views.utils import ProjectWrapper


class CoscineJSONExport(AnswersExportMixin, Export):
    """JSON export plugin for importing RDMO project data into Coscine.

    The exported JSON contains the unsigned payload plus a JWT.  The JWT signs a
    SHA-256 hash of the canonicalized unsigned payload, not the full JSON object
    including the JWT itself.
    """

    jwt_field_name = 'jwt'
    default_jwt_algorithm = 'HS256'
    allowed_jwt_algorithms = {'HS256', 'HS384', 'HS512'}
    min_jwt_secret_length = 32
    pid_base_urls = (
        'https://orcid.org/',
        'https://ror.org/',
        'https://www.dfg.de/',
    )
    http_url_schemes = {'http', 'https'}
    current_dfg_review_board_path_pattern = re.compile(
        r'^/de/ueber-uns/gremien/fachkollegien/fachsystematik/'
        r'[^/]+-(?P<section>\d+)-(?P<board>\d{2})/?$'
    )

    @staticmethod
    def canonicalize_payload(payload: dict[str, Any]) -> str:
        """Return the canonical JSON representation used for payload hashing."""
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(',', ':'),
            sort_keys=True,
        )

    @classmethod
    def build_jwt_claims(
        cls,
        payload: dict[str, Any],
        issued_at: float | None = None,
        issuer: str | None = None,
    ) -> dict[str, str | int]:
        canonical_payload = cls.canonicalize_payload(payload).encode('utf-8')

        claims: dict[str, str | int] = {
            'project_id': payload['project_id'],
            'payload_sha256': hashlib.sha256(canonical_payload).hexdigest(),
            'iat': int(time.time() if issued_at is None else issued_at),
        }

        if issuer:
            claims['iss'] = issuer

        return claims

    @classmethod
    def encode_jwt(
        cls,
        payload: dict[str, Any],
        secret: str,
        algorithm: str = default_jwt_algorithm,
        issued_at: float | None = None,
        issuer: str | None = None,
    ) -> str:
        claims = cls.build_jwt_claims(payload, issued_at=issued_at, issuer=issuer)
        return jwt.encode(claims, secret, algorithm=algorithm)

    @classmethod
    def build_pid_url(cls, external_id: Any, value_and_unit: Any) -> str | None:
        external_id = str(external_id).strip()
        value_and_unit = str(value_and_unit)

        if not external_id:
            return None

        # Convert current DFG review-board URLs to the legacy URLs expected
        # by Coscine. This must happen before is_supported_pid_url(), because
        # current DFG URLs are themselves valid supported URLs.
        coscine_dfg_url = cls.get_coscine_dfg_review_board_url(external_id)
        if coscine_dfg_url:
            return coscine_dfg_url

        if cls.is_supported_pid_url(external_id):
            return external_id

        for base_url in cls.pid_base_urls:
            if base_url in value_and_unit:
                return f'{base_url}{external_id.removeprefix(base_url)}'

    @classmethod
    def is_supported_pid_url(cls, value: str) -> bool:
        parsed_url = urlparse(value)
        return (
            parsed_url.scheme in cls.http_url_schemes
            and bool(parsed_url.netloc)
            and any(value.startswith(base_url) for base_url in cls.pid_base_urls)
        )

    @classmethod
    def get_pid_external_ids(cls, values: list[dict[str, Any]]) -> list[str]:
        external_ids = []
        for value in values or []:
            external_id = cls.build_pid_url(
                value.get('external_id', ''),
                value.get('value_and_unit', ''),
            )
            if external_id:
                external_ids.append(external_id)

        return list(dict.fromkeys(external_ids))

    @staticmethod
    @lru_cache(maxsize=1)
    def get_coscine_dfg_review_board_urls() -> dict[str, str]:
        # Coscine currently identifies DFG review boards using legacy DFG URLs
        # returned by its /api/v2/disciplines endpoint. Map current DFG URLs to
        # those identifiers for import compatibility.
        resource = (
            files('rdmo_coscine')
            .joinpath('data')
            .joinpath('coscine-dfg-disciplines-review-boards.json')
        )

        with resource.open(encoding='utf-8') as stream:
            payload = json.load(stream)

        review_board_urls = {}

        for entry in payload['data']:
            legacy_url = entry.get('uri')
            if not legacy_url:
                continue

            notation = parse_qs(urlparse(legacy_url).query).get('id', [None])[0]
            if notation:
                review_board_urls[notation] = legacy_url

        return review_board_urls

    @classmethod
    def get_dfg_review_board_notation(cls, value: Any) -> str | None:
        """Extract a notation such as ``2.22`` from a current DFG URL."""
        if not value:
            return None

        parsed_url = urlparse(str(value).strip())

        if (
            parsed_url.scheme != 'https'
            or parsed_url.hostname not in {'dfg.de', 'www.dfg.de'}
        ):
            return None

        match = cls.current_dfg_review_board_path_pattern.fullmatch(
            parsed_url.path
        )
        if match is None:
            return None

        return f"{match['section']}.{match['board']}"

    @classmethod
    def get_coscine_dfg_review_board_url(
        cls,
        external_id: Any,
    ) -> str | None:
        notation = cls.get_dfg_review_board_notation(external_id)
        if notation is None:
            return None

        return cls.get_coscine_dfg_review_board_urls().get(notation)

    def build_data_item_with_value(
        self,
        question: dict[str, Any],
        labels: list[str],
        value: str,
    ) -> dict[str, str]:
        return {
            'attribute_uri': question['attribute'],
            'question': self.stringify(question['text']),
            'set': ' '.join(labels),
            'values': value,
        }

    def build_data_items(
        self,
        question: dict[str, Any],
        labels: list[str],
        values: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        pid_external_ids = self.get_pid_external_ids(values)
        if pid_external_ids:
            return [self.build_data_item_with_value(question, labels, external_id) for external_id in pid_external_ids]

        formatted_value = self.stringify_values(values)
        return [self.build_data_item_with_value(question, labels, formatted_value)]

    def get_data(self) -> list[dict[str, str]]:
        self.project.catalog.prefetch_elements()
        project_wrapper = ProjectWrapper(self.project, self.snapshot)

        data: list[dict[str, str]] = []
        for question in project_wrapper.questions:
            set_prefixes = view_tags.get_set_prefixes({}, question['attribute'], project=project_wrapper)
            for set_prefix in set_prefixes:
                set_indexes = view_tags.get_set_indexes(
                    {},
                    question['attribute'],
                    set_prefix=set_prefix,
                    project=project_wrapper,
                )
                for set_index in set_indexes:
                    values = view_tags.get_values(
                        {},
                        question['attribute'],
                        set_prefix=set_prefix,
                        set_index=set_index,
                        project=project_wrapper,
                    )
                    labels = view_tags.get_labels(
                        {},
                        question,
                        set_prefix=set_prefix,
                        set_index=set_index,
                        project=project_wrapper,
                    )
                    result = view_tags.check_element(
                        {},
                        question,
                        set_prefix=set_prefix,
                        set_index=set_index,
                        project=project_wrapper,
                    )

                    if result:
                        data.extend(self.build_data_items(question, labels, values))

        return data

    def get_payload(self) -> dict[str, Any]:
        return {
            'version': '1.0.0',
            'import_type': 'rdmo',
            'catalog_title': self.project.catalog.title,
            'catalog_uri': self.project.catalog_uri,
            'project_id': str(self.project.id),
            'data': self.get_data(),
        }

    def get_signing_config(self) -> dict[str, str | None]:
        signing_config = getattr(settings, 'COSCINE_EXPORTS', {})
        secret = signing_config.get('jwt_secret')

        if not isinstance(secret, str) or len(secret) < self.min_jwt_secret_length:
            raise ImproperlyConfigured(
                "COSCINE_EXPORTS['jwt_secret'] must be configured as a string "
                f'with at least {self.min_jwt_secret_length} characters.'
            )

        algorithm = signing_config.get('jwt_algorithm', self.default_jwt_algorithm)

        if algorithm not in self.allowed_jwt_algorithms:
            allowed = ', '.join(sorted(self.allowed_jwt_algorithms))
            raise ImproperlyConfigured(f"COSCINE_EXPORTS['jwt_algorithm'] must be one of: {allowed}.")

        return {
            'jwt_secret': secret,
            'jwt_algorithm': algorithm,
            'jwt_issuer': signing_config.get('jwt_issuer'),
        }

    def get_export_data(self) -> dict[str, Any]:
        payload = self.get_payload()
        signing_config = self.get_signing_config()

        return {
            **payload,
            self.jwt_field_name: self.encode_jwt(
                payload,
                signing_config['jwt_secret'],
                algorithm=signing_config['jwt_algorithm'],
                issuer=signing_config['jwt_issuer'],
            ),
        }

    def render(self) -> HttpResponse:
        return render_to_json(self.project.title, self.get_export_data())
