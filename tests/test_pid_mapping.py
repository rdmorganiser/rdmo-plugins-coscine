import pytest

from rdmo_coscine.exports import CoscineJSONExport

ORCID_URL = 'https://orcid.org/0000-0002-1825-0097'
ROR_URL = 'https://ror.org/03yrm5c26'
CURRENT_DFG_URL = 'https://www.dfg.de/de/ueber-uns/gremien/fachkollegien/fachsystematik/medizin-2-22'
LEGACY_DFG_URL = 'http://www.dfg.de/dfg_profil/gremien/fachkollegien/liste/index.jsp?id=2.22'


@pytest.mark.parametrize(
    ('external_id', 'rendered_value', 'expected'),
    [
        (ORCID_URL, 'Researcher', ORCID_URL),
        (f'  {ORCID_URL}  ', 'Researcher', ORCID_URL),
        ('0000-0002-1825-0097', f'<a href="{ORCID_URL}">Researcher</a>', ORCID_URL),
        (ROR_URL, 'Organisation', ROR_URL),
        ('03yrm5c26', f'<a href="{ROR_URL}">Organisation</a>', ROR_URL),
        (CURRENT_DFG_URL, 'Medizin', LEGACY_DFG_URL),
        (f'{CURRENT_DFG_URL}/', 'Medizin', LEGACY_DFG_URL),
        (CURRENT_DFG_URL.replace('www.dfg.de', 'dfg.de'), 'Medizin', LEGACY_DFG_URL),
        ('https://www.dfg.de/example', 'DFG', 'https://www.dfg.de/example'),
        ('', 'Plain text', None),
        ('unrecognized-id', 'Plain text', None),
        ('https://example.org/identifier', 'Other identifier', None),
    ],
)
def test_pid_mapping(external_id, rendered_value, expected):
    assert CoscineJSONExport.build_pid_url(external_id, rendered_value) == expected


def test_pid_values_are_deduplicated_in_order():
    values = [
        {'external_id': ORCID_URL},
        {'external_id': ROR_URL},
        {'external_id': ORCID_URL},
        {'value_and_unit': 'Plain text'},
    ]
    assert CoscineJSONExport.get_pid_external_ids(values) == [ORCID_URL, ROR_URL]


def test_pid_values_produce_separate_data_items(exporter):
    question = {'attribute': 'https://example.org/attribute', 'text': 'Identifiers?'}
    values = [{'external_id': CURRENT_DFG_URL}, {'external_id': ORCID_URL}, {'external_id': ORCID_URL}]
    assert exporter.build_data_items(question, ['Dataset 1'], values) == [
        {
            'attribute_uri': question['attribute'],
            'question': 'Identifiers?',
            'set': 'Dataset 1',
            'values': identifier,
        }
        for identifier in [LEGACY_DFG_URL, ORCID_URL]
    ]


@pytest.mark.parametrize(
    ('values', 'expected'),
    [
        ([], ''),
        (
            [{'value_and_unit': 'Ordinary\nanswer'}, {'value_and_unit': 'Second answer'}],
            'Ordinary answer; Second answer',
        ),
    ],
)
def test_plain_text_fallback(exporter, values, expected):
    question = {'attribute': 'https://example.org/attribute', 'text': 'Question?'}
    assert exporter.build_data_items(question, [], values) == [
        {'attribute_uri': question['attribute'], 'question': 'Question?', 'set': '', 'values': expected},
    ]
