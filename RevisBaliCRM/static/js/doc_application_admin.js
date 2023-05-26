django.jQuery(document).ready(function() {
    var doc_type_selector = django.jQuery('#id_doc_type');  // the id of your doc_type field
    var product_selector = django.jQuery('#id_product');  // the id of your product field

    doc_type_selector.change(function() {
        var doc_type = django.jQuery(this).val();

        django.jQuery.ajax({
            url: 'api/products/get_products_by_product_type/',  // the url of your Django view that returns a list of products
            data: {
                'product_type': doc_type
            },
            success: function(data) {
                // assuming your view returns data as {'products': [{'id': 1, 'name': 'Product 1'}, ...]}
                product_selector.empty();
                django.jQuery.each(data.products, function(key, value) {
                    product_selector.append(django.jQuery('<option></option>').attr('value', value.id).text(value.name));
                });
                product_selector.change();  // trigger change event to refresh required_documents
            }
        });
    });

    product_selector.change(function() {
        var product_id = django.jQuery(this).val();

        django.jQuery.ajax({
            url: '/api/products/products/get_required_documents/',  // the url of your Django view that returns a list of required_documents
            data: {
                'product_id': product_id
            },
            success: function(data) {
                // update required_documents
            }
        });
    });
});
