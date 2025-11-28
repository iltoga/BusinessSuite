/* Document update page OCR check script
   Moved from customer_applications/templates/customer_applications/document_update.html
*/
(function(){
    'use strict';

    function init() {
        var ocr_check_btn = document.getElementById('ocr_check_btn_id');
        if (!ocr_check_btn) return;
        var resizedImage = document.getElementById('resized_image_id');

        ocr_check_btn.addEventListener('click', function(e) {
            var url = ocr_check_btn.dataset.ocrUrl || '/api/ocr/check/';
            var docType = ocr_check_btn.dataset.ocrDocType || '';
            var fileInput = document.querySelector('input[name="file"]');
            if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                toggleMessageDisplay(false, 'No file selected', 'ocr_check_error_id', 'ocr_check_success_id');
                return;
            }
            var formData = new FormData();
            formData.append('file', fileInput.files[0]);
            if (docType) {
                formData.append('doc_type', docType);
            }
            toggleSpinnerDisplay(true, 'ocr_check_btn_id', 'ocr_check_spinner');
            restApiCall('POST', url, formData,
                function(data){
                    var mrz = data.mrz_data;
                    var successMessage = 'File successfully checked via OCR!';
                    if (data.ai_warning) {
                        successMessage = 'OCR completed with AI warning: ' + data.ai_warning;
                    }
                    toggleMessageDisplay(true, successMessage, 'ocr_check_error_id', 'ocr_check_success_id');

                    setFormFieldValue('id_doc_number', mrz.number);
                    setFormFieldValue('id_expiration_date', mrz.expiration_date_yyyy_mm_dd);
                    setFormFieldValue('id_ocr_check', true, 'checkbox');
                    setFormFieldValue('id_metadata', JSON.stringify(mrz));
                    setFormFieldValue('id_metadata_display', JSON.stringify(mrz));
                    toggleSpinnerDisplay(false, 'ocr_check_btn_id', 'ocr_check_spinner');

                    if (data.b64_resized_image) {
                        if (resizedImage) {
                            resizedImage.src = 'data:image/jpeg;base64,' + data.b64_resized_image;
                            resizedImage.style.display = 'block';
                        }
                    }
                },
                function(error){
                    toggleMessageDisplay(false, error.message, 'ocr_check_error_id', 'ocr_check_success_id');
                    toggleSpinnerDisplay(false, 'ocr_check_btn_id', 'ocr_check_spinner');
                }
            );
        });
    }

    if (document.readyState !== 'loading') {
        init();
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }

})();
