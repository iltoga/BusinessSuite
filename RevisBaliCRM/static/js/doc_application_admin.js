var script = document.createElement('script');
script.src = 'https://code.jquery.com/jquery-3.7.0.min.js';
script.onload = function () {
    $(document).ready(function() {
        var doc_type_selector = $('#id_doc_type');  // the id of your doc_type field
        var product_selector = $('#id_product');  // the id of your product field

        doc_type_selector.change(function() {
            var doc_type = $(this).val();

            // add header bearer token
            $.ajax({
                url: 'api/products/get_products_by_product_type/'+doc_type,  // the url of your Django view that returns a list of products
                headers: {
                    'Authorization': 'Bearer ' + '0d8bc9f9d103049cea12e6b8187949a53daf2717',
                },
                success: function(data) {
                    // assuming your view returns data as {'products': [{'id': 1, 'name': 'Product 1'}, ...]}
                    product_selector.empty();
                    $.each(data.products, function(key, value) {
                        product_selector.append($('<option></option>').attr('value', value.id).text(value.name));
                    });
                    product_selector.change();  // trigger change event to refresh required_documents
                }
            });
        });

        product_selector.change(function() {
            var product_id = $(this).val();

            $.ajax({
                url: '/api/products/get_product_by_id/',  // the url of your Django view that returns a list of required_documents
                data: {
                    'product_id': product_id
                },
                success: function(data) {
                    // update required_documents
                }
            });
        });
    });
};
document.getElementsByTagName('head')[0].appendChild(script);
