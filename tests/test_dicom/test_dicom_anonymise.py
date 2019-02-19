from pymedphys.dicom import anonymise_dicom, IDENTIFYING_TAGS
from pymedphys.dicom import BaselineDicomDictionary


def test_tags_to_anonymise_in_dicom_dict_baseline():
    keywords_in_dicom_dict_baseline = \
        [val[4] for val in BaselineDicomDictionary.values()]
    assert set(IDENTIFYING_TAGS).issubset(keywords_in_dicom_dict_baseline)
