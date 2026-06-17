import hashlib
import json
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

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

    jwt_field_name = "jwt"
    default_jwt_algorithm = "HS256"
    allowed_jwt_algorithms = {"HS256", "HS384", "HS512"}
    min_jwt_secret_length = 32

    @staticmethod
    def canonicalize_payload(payload):
        """Return the canonical JSON representation used for payload hashing."""
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def build_jwt_claims(cls, payload, issued_at=None, issuer=None):
        canonical_payload = cls.canonicalize_payload(payload).encode("utf-8")

        claims = {
            "project_id": payload["project_id"],
            "payload_sha256": hashlib.sha256(canonical_payload).hexdigest(),
            "iat": int(time.time() if issued_at is None else issued_at),
        }

        if issuer:
            claims["iss"] = issuer

        return claims

    @classmethod
    def encode_jwt(cls, payload, secret, algorithm=default_jwt_algorithm, issued_at=None, issuer=None):
        claims = cls.build_jwt_claims(payload, issued_at=issued_at, issuer=issuer)
        return jwt.encode(claims, secret, algorithm=algorithm)

    def build_data_item(self, question, labels, values):
        return {
            "attribute_uri": question["attribute"],
            "question": self.stringify(question["text"]),
            "set": " ".join(labels),
            "values": self.stringify_values(values),
        }

    def get_data(self):
        self.project.catalog.prefetch_elements()
        project_wrapper = ProjectWrapper(self.project, self.snapshot)

        data = []
        for question in project_wrapper.questions:
            set_prefixes = view_tags.get_set_prefixes({}, question["attribute"], project=project_wrapper)
            for set_prefix in set_prefixes:
                set_indexes = view_tags.get_set_indexes(
                    {},
                    question["attribute"],
                    set_prefix=set_prefix,
                    project=project_wrapper,
                )
                for set_index in set_indexes:
                    values = view_tags.get_values(
                        {},
                        question["attribute"],
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
                        data.append(self.build_data_item(question, labels, values))

        return data

    def get_payload(self):
        return {
            "version": "1.0.0",
            "import_type": "rdmo",
            "catalog_title": self.project.catalog.title,
            "catalog_uri": self.project.catalog_uri,
            "project_id": str(self.project.id),
            "data": self.get_data(),
        }

    def get_signing_config(self):
        signing_config = getattr(settings, "COSCINE_EXPORTS", {})
        secret = signing_config.get("jwt_secret")

        if not isinstance(secret, str) or len(secret) < self.min_jwt_secret_length:
            raise ImproperlyConfigured(
                "COSCINE_EXPORTS['jwt_secret'] must be configured as a string "
                f"with at least {self.min_jwt_secret_length} characters."
            )

        algorithm = signing_config.get("jwt_algorithm", self.default_jwt_algorithm)

        if algorithm not in self.allowed_jwt_algorithms:
            allowed = ", ".join(sorted(self.allowed_jwt_algorithms))
            raise ImproperlyConfigured("COSCINE_EXPORTS['jwt_algorithm'] must be one of: " f"{allowed}.")

        return {
            "jwt_secret": secret,
            "jwt_algorithm": algorithm,
            "jwt_issuer": signing_config.get("jwt_issuer"),
        }

    def get_export_data(self):
        payload = self.get_payload()
        signing_config = self.get_signing_config()

        return {
            **payload,
            self.jwt_field_name: self.encode_jwt(
                payload,
                signing_config["jwt_secret"],
                algorithm=signing_config["jwt_algorithm"],
                issuer=signing_config["jwt_issuer"],
            ),
        }

    def render(self):
        return render_to_json(self.project.title, self.get_export_data())
