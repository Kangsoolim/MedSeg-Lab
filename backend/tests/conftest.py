import pytest
from backend.config import settings

COURSE_TESTS={
 'test_all_epochs_match_independently_read_original_csv',
 'test_key_epochs_patient_counts_and_real_assets',
 'test_all_formats_real_values_source_receipt_and_conflict',
 'test_vendor_source_identity',
 'test_course_partition_and_heldout_guard',
 'test_supplied_patient_identity_conflict_is_rejected',
}

DEMO_TESTS={
 'test_legacy_history_projection_never_rewrites_original_records',
 'test_frozen_records_identify_the_selected_method',
 'test_ids_are_unique_across_training_inference_and_reference_types',
 'test_imported_analysis_is_not_mislabeled_as_frozen',
 'test_inference_volume_time_and_frozen_numeric_schema',
}
def pytest_collection_modifyitems(items):
    from backend.config import ROOT
    course=bool(settings().get('source_root'))
    demo=(ROOT/'frontend/public/demo/index.json').is_file()
    for item in items:
        name=getattr(item,'originalname',None) or item.name
        if name in COURSE_TESTS and not course:
            item.add_marker(pytest.mark.skip(reason='Explicit course integration profile not configured'))
        if name in DEMO_TESTS and not demo:
            item.add_marker(pytest.mark.skip(reason='Optional private frozen demo package absent'))
