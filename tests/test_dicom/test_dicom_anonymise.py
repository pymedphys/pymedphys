from pymedphys.dicom import IDENTIFYING_KEYWORDS
from pymedphys.dicom import BaselineDicomDictionary


def test_tags_to_anonymise_in_dicom_dict_baseline():
    baseline_keywords = [val[4] for val in BaselineDicomDictionary.values()]
    assert set(IDENTIFYING_KEYWORDS).issubset(baseline_keywords)
