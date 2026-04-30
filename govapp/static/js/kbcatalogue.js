var kbcatalogue = { 
    var: {
         catalogue_data_url: "/api/catalogue/entries/",
         catalogue_permission_url: "/api/catalogue/permission/",
         catalogue_layer_symbology_url: "/api/catalogue/layers/symbologies/",
         catalogue_status: {
            1: {"name": "New Draft", "colour": "darkgray", "class": "badge bg-secondary"},
            2: {"name": "Locked", "colour": "green", "class": "badge bg-success"},
            3: {"name": "Declined", "colour": "darkgray", "class": "badge bg-danger"},
            4: {"name": "Draft", "colour": "darkgray", "class": "badge bg-secondary"},
            5: {"name": "Pending", "colour": "darkgray", "class": "badge bg-warning"}
        },
        spatial_type: {
            1: "Spatial File",
            2: "Subscription WFS",
            3: "Subscription WMS",
            4: "Subscription PostGIS",
            5: "Custom Query"
        },
        catalogue_date_format: "dd/mm/yyyy",
        catalogue_table_date_format: "DD MMM YYYY HH:mm:ss",
    },
    
    init_dashboard: function() { 

        $('#catalogue-lastupdatedfrom').datepicker({ dateFormat: 'yyyy-mm-dd', 
                                                    format: 'dd/mm/yyyy',
                                                });
        $('#catalogue-lastupdatedto').datepicker({  dateFormat: 'yyyy-mm-dd', 
                                                    format: 'dd/mm/yyyy',
                                                });
        
        $('#catalogue-custodian').select2({
            placeholder: 'Select an option',
            minimumInputLength: 2,
            allowClear: true,
            width: $( this ).data( 'width' ) ? $( this ).data( 'width' ) : $( this ).hasClass( 'w-100' ) ? '100%' : 'style',
            theme: 'bootstrap-5',
            ajax: {
                url: "/api/catalogue/custodians/",
                dataType: 'json',
                quietMillis: 100,
                data: function (params, page) {
                   
                    return {
                        search: params.term,                        
                    };
                },    
                  processResults: function (data) {
                    // Transforms the top-level key of the response object from 'items' to 'results'
                    var results = [];
                    $.each(data.results, function(index, item){
                      results.push({
                        id: item.id,
                        text: item.name
                      });
                    });
                    return {
                        results: results
                    };
                  }                  
            },
        });

        $('#catalogue-assignedto').select2({
            placeholder: 'Select an option',
            minimumInputLength: 2,
            allowClear: true,
            width: $( this ).data( 'width' ) ? $( this ).data( 'width' ) : $( this ).hasClass( 'w-100' ) ? '100%' : 'style',
            theme: 'bootstrap-5',
            ajax: {
                url: "/api/accounts/users/",
                dataType: 'json',
                quietMillis: 100,
                data: function (params, page) {
                    return {
                        q: params.term,
                    };
                },
                  processResults: function (data) {
                    // Transforms the top-level key of the response object from 'items' to 'results'
                    var results = [];
                    $.each(data.results, function(index, item){
                      results.push({
                        id: item.id,
                        text: item.first_name+' '+item.last_name
                      });
                    });
                    return {
                        results: results
                    };
                }
            },
        });

        $( "#catalogue-filter-btn" ).click(function() {
            kbcatalogue.get_catalogue();
        });

        $("#catalogue-limit").change(function() {
            common_pagination.var.current_page=0;
            kbcatalogue.get_catalogue();
        });
        $("#catalogue-order-by").change(function() {
            common_pagination.var.current_page=0;
            kbcatalogue.get_catalogue();
        });
        $("#catalogue-ordering-direction").change(function() {
            common_pagination.var.current_page=0;
            kbcatalogue.get_catalogue();
        });

        utils.enter_keyup($('#catalogue-name'), kbcatalogue.get_catalogue);
        utils.enter_keyup($('#catalogue-description'), kbcatalogue.get_catalogue);
        utils.enter_keyup($('#catalogue-number'), kbcatalogue.get_catalogue);
        
        kbcatalogue.get_catalogue();
        
        // *** Upload Catalogue ***
        // Show modal
        $( "#upload-catalogue-btn" ).click(function() {
            $('#modal_upload_catalogue').modal('show');
        });
        // Start uploading
        $("#fileInput").change(function(){
            var files = $("#fileInput")[0].files;
            // for (var i = 0; i < files.length; i++) {
                // Show progress bar
                // $("#progressBars").append('<div class="progress mt-2"><div class="progress-bar" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div></div>');
            // }
            kbcatalogue.uploadFiles(files);
        });
        // Select by drag-and-drop
        $("#modalContent").on('dragover', function(event) {
            event.preventDefault();
            $("#modalContent").addClass('dragover');
        });
        $("#modalContent").on('dragleave drop', function(event) {
            event.preventDefault();
            $("#modalContent").removeClass('dragover');
        });
        $("#modalContent").on('drop', function(event) {
            event.preventDefault();
            $("#modalContent").removeClass('dragover');
            var files = event.originalEvent.dataTransfer.files;
            kbcatalogue.uploadFiles(files);
        });
        $("#cancel_upload_catalogue_btn").on('click', function(event){
            kbcatalogue.cancelUploadCatalogue();
        }),
        $("#submit_upload_catalogue_btn").on('click', function(event){
            kbcatalogue.submitUploadCatalogue();
        })
        $('#modal_upload_catalogue').on('hidden.bs.modal', function (e) {
            kbcatalogue.modalClosed()
        });
    },

    init_catalogue_item: function() { 
        $("#catalogue-entry-symbology-btn-save").click(function() {
            kbcatalogue.save_symbology('save');
        });
        $("#catalogue-entry-symbology-btn-save-exit").click(function() {
            kbcatalogue.save_symbology('save-and-exit');
        });

        $("#catalogue-lock").click(function() {
            kbcatalogue.change_catalogue_status('lock');
        });
        $("#catalogue-unlock").click(function() {
            kbcatalogue.change_catalogue_status('unlock');
        });
        $("#catalogue-assigned-to-btn").click(function() {
            kbcatalogue.set_assigned_to();
        });

        let select2_setting = {
            placeholder: "User's name",
            minimumInputLength: 2,
            allowClear: true,
            dropdownParent: $('#ManageEditorsModal'),
            width: $( this ).data( 'width' ) ? $( this ).data( 'width' ) : $( this ).hasClass( 'w-100' ) ? '100%' : 'style',
            theme: 'bootstrap-5',
            ajax: {
                url: "/api/accounts/users/",
                dataType: 'json',
                quietMillis: 100,
                data: function (params, page) {
                    return {
                        q: params.term,
                    };
                },
                  processResults: function (data) {
                    // Transforms the top-level key of the response object from 'items' to 'results'
                    var results = [];
                    $.each(data.results, function(index, item){
                      results.push({
                        id: item.id,
                        text: `${item.first_name} ${item.last_name} (${item.email})`
                      });
                    });
                    return {
                        results: results
                    };
                }
            },
        };

        $( "#catalogue-manage-editors-btn" ).click(function(){
            kbcatalogue.get_catalogue_entry_permissions();
            $('#manage-editors-search').val("").trigger('change');
            $('#manage-popup-error').hide();
            $('#ManageEditorsModal').modal('show');
        });

        $( '#catalogue-show-permission-btn' ).click(function(){
            kbcatalogue.get_catalogue_entry_permissions(false);
            $('#manage-editors-add-area').hide();
            $('#manage-popup-error').hide();
            $('#ManageEditorsModal').modal('show');
        });
        
        $('#manage-editors-search').select2(select2_setting);
        
        $('#manage-editors-add-btn').click(function(e){
            kbcatalogue.add_catalogue_editor($('#manage-editors-search').val());
        });
    },

    change_catalogue_status: function(status) {        
        $('#loadingOverlay').fadeIn();

        var status_url = "lock";
        if (status == 'unlock') {
            status_url = 'unlock';
        }

        var catalogue_entry_id = $('#catalogue_entry_id').val();
        var csrf_token = $("#csrfmiddlewaretoken").val();
        var pagetab = $('#pagetab').val();

        $.ajax({
            url: kbcatalogue.var.catalogue_data_url+catalogue_entry_id+"/"+status_url+"/",
            //method: 'POST',
            type: 'POST',
            //dataType: 'json',
            headers: {'X-CSRFToken' : csrf_token},
            contentType: 'application/json',
            success: function (response, status, xhr) {
                // triggered when the server responds with a status code in the range of 200 to 299 (inclusive) or 304.
                window.location = "/catalogue/entries/"+catalogue_entry_id+"/"+pagetab+"/";       
            },
            error: function (xhr, status, error) {
                // executed when the server responds with a status code outside the 200-299 range, such as 400 (Bad Request), 404 (Not Found), or 500 (Internal Server Error). 
                console.log(xhr)
                try {
                    // const errorResponse = JSON.parse(xhr.responseText);
                    const errorResponse = xhr.responseText
                    if (errorResponse) {
                        common_entity_modal.show_alert(errorResponse);
                    } else {
                        common_entity_modal.show_alert("An error occurred");
                    }
                } catch (e) {
                    common_entity_modal.show_alert("Error Changing Status");
                }
            },
            complete: function(xhr, status){
                $('#loadingOverlay').fadeOut();
            }
        });
    },

    set_assigned_to: function() { 
        var catalogueassignedto = $('#catalogue-assigned-to').val();
        var catalogue_entry_id = $('#catalogue_entry_id').val();
        var csrf_token = $("#csrfmiddlewaretoken").val();
        var pagetab = $('#pagetab').val();

        if (catalogueassignedto == null || catalogueassignedto.length == 0 || catalogueassignedto == "") {
            common_entity_modal.show_alert("Please select an assigned-to person first.");
            return
        }

        $('#loadingOverlay').fadeIn();
        $.ajax({
            url: kbcatalogue.var.catalogue_data_url+catalogue_entry_id+"/assign/"+catalogueassignedto+"/",
            type: 'POST',
            headers: {'X-CSRFToken' : csrf_token},
            contentType: 'application/json',
            success: function (response) {
                var html = '';
                
                window.location = "/catalogue/entries/"+catalogue_entry_id+"/"+pagetab+"/"; 
            },
            error: function (error) {
                common_entity_modal.show_alert("ERROR Setting assigned person.");
            },
            complete: function(xhr, status){
                $('#loadingOverlay').fadeOut();
            }
        });
    },

    save_symbology: function(save_status) {
        let catalogue_id = $('#catalogue_entry_id').val();
        let cataloguesymbologydefinition = $('#catalogue-entry-symbology-definition').val();
        let use_raw = $('#raw-parameter').prop("checked")
        let post_data = {"sld": cataloguesymbologydefinition, "use_raw": use_raw};
        let layer_symbology_id = $('#catalogue-entry-symbology-definition-id').val();
        let csrf_token = $("#csrfmiddlewaretoken").val();
        let pagetab = $('#pagetab').val();
        let url = kbcatalogue.var.catalogue_layer_symbology_url + layer_symbology_id + "/"

        $.ajax({
            url: url,
            type: 'PUT',
            headers: {'X-CSRFToken' : csrf_token},
            data: post_data,
            success: function (response) {
                if (save_status == 'save-and-exit') {
                    window.location = '/catalogue/entries/';
                } else {
                    window.location = "/catalogue/entries/" + catalogue_id + "/" + pagetab + "/"; 
                }
            },
            error: function (error) {
                common_entity_modal.show_alert("ERROR Saving."); 
            },
        });
    },

    addDateTimeToFilename: function(filename) {
        // Get current date and time
        const currentDate = new Date();
    
        // Format date
        const year = currentDate.getFullYear();
        const month = String(currentDate.getMonth() + 1).padStart(2, '0'); // Pad month with leading zero
        const day = String(currentDate.getDate()).padStart(2, '0'); // Pad day with leading zero
        const hours = String(currentDate.getHours()).padStart(2, '0'); // Pad hours with leading zero
        const minutes = String(currentDate.getMinutes()).padStart(2, '0'); // Pad minutes with leading zero
        const seconds = String(currentDate.getSeconds()).padStart(2, '0'); // Pad seconds with leading zero
    
        // Insert date and time between filename and extension
        const extensionIndex = filename.lastIndexOf('.');
        const newFilename = filename.slice(0, extensionIndex) + '.' + year + month + day + '_' + hours + minutes + seconds + filename.slice(extensionIndex);
    
        return newFilename;
    },

    createProgressBar: function(fileName, newFileName) {
        console.log('creating progress bar')
        var progressBarContainer = $('<div class="progress-container mt-2"></div>');
        var progressBarRow = $('<div class="row  d-flex align-items-center"></div>');
        var fileNameColumn = $('<div class="col-6"></div>');
        // var progressBarColumn = $('<div class="col-5"></div>');
        var progressBarColumn = $('<div class="col-4"></div>');
        var progressBarTextColumn = $('<div class="col-1"><span class="progress-text"></span></div>');
        var deleteIconColumn = $('<div class="col-1"></div>');
    
        var progressBar = $('<div class="progress"><div class="progress-bar" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div></div>');
        var fileNameElement = $('<div class="file-name">' + fileName + '</div>');
        var deleteIcon = $('<span class="delete-icon" data-newFileName="' + newFileName + '"><svg width="24" height="24" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 12L12 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M12 12L4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></span>')
    
        fileNameColumn.append(fileNameElement);
        progressBarColumn.append(progressBar);
        deleteIconColumn.append(deleteIcon);
    
        progressBarRow.append(fileNameColumn);
        progressBarRow.append(progressBarTextColumn);
        progressBarRow.append(progressBarColumn);
        progressBarRow.append(deleteIconColumn);
    
        progressBarContainer.append(progressBarRow);
    
        return {
            progressBar: progressBar,
            progressBarContainer: progressBarContainer,
            deleteIcon: deleteIcon
        };
    },
    
    deleteFile: function(fileName) {
        // Make an AJAX request to delete the file
        var csrf_token = $("#csrfmiddlewaretoken").val();
        var xhr = $.ajax({
            url: kbcatalogue.var.catalogue_data_url + "delete_file/", // Change the URL to your delete file endpoint
            type: 'POST',
            headers: {'X-CSRFToken' : csrf_token}, // Include CSRF token in headers
            data: {'newFileName': fileName},
            success: function(data){

            },
            error: function(xhr, status, error) {
                console.error("Error deleting file:", error);
            }
        });
    },
    modalClosed: function(){
        kbcatalogue.cancelUploadCatalogue();
    },
    submitUploadCatalogue: function(){
        var progressBarContainer = $('#progressBars')
        progressBarContainer.empty();
    },
    cancelUploadCatalogue: function(){
        $(".cross-sign").each(function() {
            var newFilename = $(this).data("newfilename");
            kbcatalogue.deleteFile(newFilename);
        });
        var progressBarContainer = $('#progressBars')
        progressBarContainer.empty();
    },

    // Function for uploading files using chunked upload (10 MB per chunk).
    // Each file is sliced into chunks and sent sequentially. Multiple files
    // are uploaded in parallel (one chunk-loop per file).
    uploadFiles: function(files) {
        var CHUNK_SIZE = 10 * 1024 * 1024; // 10 MB per chunk
        var csrf_token = $("#csrfmiddlewaretoken").val();

        for (var i = 0; i < files.length; i++) {
            var fileName = files[i].name;
            var newFileName = kbcatalogue.addDateTimeToFilename(fileName);

            // Generate progressbar per file
            var { progressBar, progressBarContainer, deleteIcon } = kbcatalogue.createProgressBar(fileName, newFileName);
            $("#progressBars").append(progressBarContainer);

            (function(file, newFileName, progressBar, progressBarContainer, deleteIcon) {
                var cancelled = false;
                var totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE));

                // Cancel / delete button
                deleteIcon.on('click', function() {
                    cancelled = true;
                    kbcatalogue.deleteFile(newFileName);
                    progressBarContainer.fadeOut('slow', function() { $(this).remove(); });
                });

                function uploadChunk(chunkIndex) {
                    if (cancelled) return;

                    var start = chunkIndex * CHUNK_SIZE;
                    var end = Math.min(start + CHUNK_SIZE, file.size);
                    var chunkBlob = file.slice(start, end);

                    var formData = new FormData();
                    formData.append('chunk', chunkBlob, file.name);
                    formData.append('newFileName', newFileName);
                    formData.append('chunkIndex', chunkIndex);
                    formData.append('totalChunks', totalChunks);
                    formData.append('totalSize', file.size);

                    $.ajax({
                        url: kbcatalogue.var.catalogue_data_url + "upload_file/",
                        type: 'POST',
                        headers: {'X-CSRFToken': csrf_token},
                        data: formData,
                        cache: false,
                        contentType: false,
                        processData: false,
                        success: function(response) {
                            if (cancelled) return;
                            var percent = ((chunkIndex + 1) / totalChunks) * 100;
                            progressBar.find(".progress-bar").width(percent + '%');
                            progressBar.find(".progress-bar").attr('aria-valuenow', percent);
                            progressBarContainer.find(".progress-text").text(percent.toFixed(0) + '%');
                            if (!response.complete) {
                                uploadChunk(chunkIndex + 1);
                            }
                        },
                        error: function(xhr) {
                            if (cancelled) return;
                            var errorResponse;
                            try { errorResponse = JSON.parse(xhr.responseText); } catch(e) { errorResponse = {error: 'Upload failed.'}; }
                            progressBar.fadeOut('slow', function() {
                                progressBar.replaceWith($('<span class="error-message">' + errorResponse.error + '</span>'));
                            });
                        }
                    });
                }

                uploadChunk(0);
            })(files[i], newFileName, progressBar, progressBarContainer, deleteIcon);
        }
    },

    get_catalogue: function(params_str) {
        if (!params_str){
            params = {
                name__icontains: $('#catalogue-name').val(),
                status: $('#catalogue-status').val(),
                description__icontains: $('#catalogue-description').val(),
                custodian: +$('#catalogue-custodian').val(),
                assigned_to: +$('#catalogue-assignedto').val(),
                updated_after: utils.convert_date_format($('#catalogue-lastupdatedfrom').val(), kbcatalogue.var.catalogue_date_format, hh="00", mm="00", ss="00"),
                updated_before: utils.convert_date_format($('#catalogue-lastupdatedto').val(), kbcatalogue.var.catalogue_date_format, hh="23", mm="59", ss="59"),
                id: $('#catalogue-number').val().replace("PE", ""),
                limit: $('#catalogue-limit').val(),
                order_by: $('#catalogue-order-by').val(),
                ordering_direction: $('#catalogue-ordering-direction').val(),
                type_in: $('#ce_types_to_display').val()
            }
            params_str = utils.make_query_params(params);
        }

        $.ajax({
            url: kbcatalogue.var.catalogue_data_url + "?" + params_str,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                var html = '';
                
                if (response != null) {
                    if (response.results.length > 0) {
                        for (let i = 0; i < response.results.length; i++) {
                            let catalogue_entry = response.results[i]
                            assigned_to_friendly = "";

                            if (catalogue_entry.assigned_to_first_name != null) {
                                assigned_to_friendly = catalogue_entry.assigned_to_first_name;
                                if (catalogue_entry.assigned_to_last_name != null) {
                                    assigned_to_friendly += " "+catalogue_entry.assigned_to_last_name;
                                }
                            } 
                            
                            if (assigned_to_friendly.replace(" ","").length == 0) {
                                if (catalogue_entry.assigned_to_email != null) {
                                    assigned_to_friendly = catalogue_entry.assigned_to_email;
                                }
                            }

                            button_json = '{"id": "'+catalogue_entry.id+'"}'
                            html += "<tr>";
                            html += "<td>CE" + catalogue_entry.id + "</td>";
                            html += "<td>" + catalogue_entry.name + "</td>";
                            html += "<td>" + kbcatalogue.var.spatial_type[catalogue_entry.type] + "</td>";
                            html += "<td>" + (catalogue_entry.permission_type == 1 ? utils.public_icon() + catalogue_entry.permission_type_str: utils.restricted_icon() + catalogue_entry.permission_type_str) + "</td>"
                            html += "<td>" + (catalogue_entry.default_crs != null ? catalogue_entry.default_crs : "") + "</td>"
                            html += "<td>" + (catalogue_entry.custodian_name != null ? catalogue_entry.custodian_name : "") + "</td>"
                            html += "<td><span class='" + kbcatalogue.var.catalogue_status[catalogue_entry.status].class + "'>" + kbcatalogue.var.catalogue_status[catalogue_entry.status].name + "<span></td>";
                            html += "<td>" + catalogue_entry.updated_at + "</td>";
                            html += "<td>" + assigned_to_friendly + "</td>";
                            html += "<td class='text-end'>";
                            html += "<a class='btn btn-primary btn-sm' href='/catalogue/entries/" + catalogue_entry.id + "/details/'>View</a>";
                            // html += "<button class='btn btn-secondary btn-sm ml-1'>History</button>";
                            html += "</td>";
                            html += "<tr>";
                        }

                        $('#publish-tbody').html(html);
                        $('.publish-table-button').hide();

                    } else {
                        $('#publish-tbody').html("<tr><td colspan='9' class='text-center'>No results found</td></tr>");
                    }

                    common_pagination.init(response.count, params, kbcatalogue.get_catalogue, $('#paging_navi'));
                } else {
                      $('#publish-tbody').html("<tr><td colspan='9' class='text-center'>No results found</td></tr>");
                }

                $( ".publish-to-geoserver-btn" ).click(function() {
                    var btndata_json = $(this).attr('data-json');
                    var btndata = JSON.parse(btndata_json);

                    kbpublish.publish_to_geoserver(btndata.id);
                });     
                
                $( ".publish-to-cddp-btn" ).click(function() {
                    var btndata_json = $(this).attr('data-json');
                    var btndata = JSON.parse(btndata_json);
                    kbpublish.publish_to_cddp(btndata.id);
                });                    
            },
            error: function (error) {
                $('#save-publish-popup-error').html("Error Loading publish data");
                $('#save-publish-popup-error').show();
                $('#save-publish-tbody').html('');
            },
        });    
    },
    get_catalogue_entry_permissions: function(permissioned=true){
        var catalogue_id = $('#catalogue_entry_id').val();
        $.ajax({
            url: kbcatalogue.var.catalogue_permission_url + "?catalogue_entry=" + catalogue_id,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                if (response != null && response.length > 0) {
                    $('#manage-editors-tbody').empty();
                    for (let i = 0; i < response.length; i++) {
                        let catalogue_entry_permission = response[i]
                        button_json = '{"id": "' + catalogue_entry_permission.id + '"}'

                        let tr_elem = $('<tr>')
                        tr_elem.append($('<td>').text(catalogue_entry_permission.id))
                        tr_elem.append($('<td>').text(catalogue_entry_permission.first_name))
                        tr_elem.append($('<td>').text(catalogue_entry_permission.last_name))
                        tr_elem.append($('<td>').text(catalogue_entry_permission.email))
                        tr_elem.append($('<td class="text-center">').append(catalogue_entry_permission.active ? '<img class="yes-no-icon" src="/static/admin/img/icon-yes.svg" alt="True">' : '<img class="yes-no-icon" src="/static/admin/img/icon-no.svg" alt="False">'))
                        tr_elem.append($('<td>').text(catalogue_entry_permission.access_permission_label))
                        tr_elem.append(permissioned ? $(`<td class='text-center'><button class='btn btn-danger btn-sm manage-editors-delete' data-json='${button_json}'>Delete</button></td>`) : $('<td>'))
                        $('#manage-editors-tbody').append(tr_elem);
                    }

                    $(".manage-editors-delete").click(function() {
                        console.log($(this).attr('data-json'));
                        var btndata_json = $(this).attr('data-json');
                        var btndata = JSON.parse(btndata_json);
                        kbcatalogue.delete_catalogue_editors(btndata.id);
                    });
                } else {
                      $('#manage-editors-tbody').html("<tr><td colspan='7' class='text-center'>No results found</td></tr>");
                }
            },
            error: function (error) {
                $('#manage-popup-error').text(error.responseText);
                $('#manage-popup-error').show();
                $('#manage-editors-tbody').html('');
            },
        });
    },
    delete_catalogue_editors: function(permission_id) {        
        // var catalogue_id = $('#catalogue_entry_id').val();
        var csrf_token = $("#csrfmiddlewaretoken").val();

        $.ajax({
            url: kbcatalogue.var.catalogue_permission_url+permission_id+"/",
            type: 'DELETE',
            headers: {'X-CSRFToken' : csrf_token},
            contentType: 'application/json',
            success: function (response) {
                kbcatalogue.get_catalogue_entry_permissions();
            },
            error: function (error) {
                $('#manage-popup-error').text(error.responseText);
                $('#manage-popup-error').show();
            },
        });


    },
    add_catalogue_editor: function(user_id) {        
        var catalogue_id = $('#catalogue_entry_id').val();
        var user_access_permission_value = $('#user-access-permission').val();
        var csrf_token = $("#csrfmiddlewaretoken").val();

        $.ajax({
            url: kbcatalogue.var.catalogue_permission_url,
            type: 'POST',
            data: JSON.stringify({
                'user':user_id,
                'catalogue_entry':catalogue_id,
                'access_permission': user_access_permission_value
            }),
            headers: {'X-CSRFToken' : csrf_token},
            contentType: 'application/json',
            success: function (response) {
                console.log(response);
                kbcatalogue.get_catalogue_entry_permissions();
            },
            error: function (error) {
                $('#manage-popup-error').text(JSON.parse(error.responseText).user[0]);
                $('#manage-popup-error').show();
            },
        });
    },
}