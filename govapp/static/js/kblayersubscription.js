var kblayersubscription = { 
    var: {
        layersubscription_data_url: '/api/catalogue/layers/subscriptions/',
        layersubscription_date_format: "dd/mm/yyyy",
        publish_workspace_url: '/api/publish/workspaces/',
        subscription_table_date_format: "DD MMM YYYY HH:mm:ss",
        workspace_map: {}, // will be filled later
        subscription_type_map: {1:"WMS", 2:"WFS", 3:"POST GIS"},
        ssl_mode_map: {"disable":"DISABLE", "allow":"ALLOW", "prefer":"PREFER", "require":"REQUIRE", "verify_ca":"VERIFY CA", "verify_full":"VERIFY FULL"},
        status_map: {
            1: {"name": "NEW DRAFT", "class": "badge badge-pill bg-secondary"},
            2: {"name": "LOCKED", "class": "badge badge-pill bg-success"},
            3: {"name": "DECLINED", "class": "badge badge-pill bg-danger"},
            4: {"name": "DRAFT", "class": "badge badge-pill bg-secondary"},
            5: {"name": "PENDING", "class": "badge badge-pill bg-warning"}
        },
        required_fields:{
            1:['type', 'workspace', 'name', 'description', 'enabled', 'url', 
                'connection_timeout', 'max_connections', 'read_timeout', 'ssl_mode',],
            2:['type', 'workspace', 'name', 'description', 'enabled', 'url', 
                'connection_timeout', 'ssl_mode',],
            3:['type', 'workspace', 'name', 'description', 'enabled', 'host', 'port', 
                'database', 'schema', 'connection_timeout', 
                'max_connections', 'min_connections', 'fetch_size', 'ssl_mode',]},
        optional_fields:['username', 'userpassword'],
        default_connection_timout: 10000,
        default_read_timout: 10000,
        default_max_concurrent_connections: 6,
        default_mim_concurrent_connections: 1,
        default_fetch_size: 1000,

        // for view  page
        subscription_save_url: '/api/catalogue/layers/subscriptions/',
        log_communication_type_url:"/api/logs/communications/type/",
        communication_type: null,
    
        source_layers: []
    },
    init_dashboard: function() { 

        $('#subscription-updated-from').datepicker({ 
            dateFormat: kblayersubscription.var.layersubscription_date_format, 
            format: kblayersubscription.var.layersubscription_date_format,
        });
        $('#subscription-updated-to').datepicker({  
            dateFormat: kblayersubscription.var.layersubscription_date_format, 
            format: kblayersubscription.var.layersubscription_date_format,
        });

        $( "#subscription-filter-btn" ).click(function() {
            kblayersubscription.get_layer_subscription();
        });
        $( "#subscription-limit" ).change(function() {
            common_pagination.var.current_page=0;
            kblayersubscription.get_layer_subscription();
        });
        $( "#subscription-order-by" ).change(function() {
            common_pagination.var.current_page=0;
            kblayersubscription.get_layer_subscription();
        });
        $("#subscription-ordering-direction").change(function() {
            common_pagination.var.current_page=0;
            kblayersubscription.get_layer_subscription();
        });
        $( "#subscription-new-btn" ).click(function() {
            kblayersubscription.show_new_subscription_modal();
        });

        $('#subscription-assignedto').select2({
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

        utils.enter_keyup($('#subscription-name'), kblayersubscription.get_layer_subscription);
        utils.enter_keyup($('#subscription-description'), kblayersubscription.get_layer_subscription);
        utils.enter_keyup($('#subscription-number'), kblayersubscription.get_layer_subscription);

        kblayersubscription.get_workspace(kblayersubscription.get_layer_subscription);
    },
    get_layer_subscription: function(param_str){
        order_by = $('#subscription-order-by').val()
        ordering_direction = $('#subscription-ordering-direction').val()
        if (ordering_direction === 'desc'){
            order_by = '-' + order_by
        }
        if(!param_str){
            params = {
                limit: $('#subscription-limit').val(),
                order_by: order_by,
                name__icontains: $('#subscription-name').val(),
                workspace: $('#subscription-workspace').val(),
                enabled: $('#subscription-enabled').val(),
                updated_after: utils.convert_date_format($('#subscription-updated-from').val(), kblayersubscription.var.layersubscription_date_format, hh="00", mm="00", ss="00"),
                updated_before: utils.convert_date_format($('#subscription-updated-to').val(), kblayersubscription.var.layersubscription_date_format,hh="23", mm="59", ss="59"),
                type: $('#subscription-type').val(),
                description__icontains: $('#subscription-description').val(),
                id: $('#subscription-number').val(),
                assigned_to: +$('#subscription-assignedto').val(),
            }
            
            param_str = utils.make_query_params(params);
        }

        $.ajax({
            url: kblayersubscription.var.layersubscription_data_url+"?"+param_str,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                if(!response || !response.results){
                    table.message_tbody($('#subscription-tbody'), "No results found");
                    return;
                }
                for(let i in response.results){
                    let layer_subscription = response.results[i]
                    layer_subscription['created_at'] = utils.convert_datetime_format(layer_subscription.created_at, kblayersubscription.var.subscription_table_date_format);
                    layer_subscription['type_str'] = kblayersubscription.var.subscription_type_map[+layer_subscription.type];
                    layer_subscription['workspace_str'] = kblayersubscription.var.workspace_map[+layer_subscription.workspace];
                    layer_subscription['status_str'] = kblayersubscription.var.status_map[+layer_subscription.status].name;
                    layer_subscription['assigned_to_name'] = null;
                    if(layer_subscription['assigned_to_first_name'])
                        layer_subscription['assigned_to_name'] = layer_subscription['assigned_to_first_name'] + ' ' + layer_subscription['assigned_to_last_name'];
                }

                // Construct the table
                $('#subscription-tbody').empty()
                for(let i in response.results){
                    let layer_subscription = response.results[i]

                    let row = $('<tr>')
                    row.append($('<td>').text(layer_subscription.id))
                    row.append($('<td>').text(layer_subscription.name))
                    row.append($('<td>').append($('<span>').addClass(kblayersubscription.var.status_map[+layer_subscription.status].class).text(layer_subscription.status_str)))
                    row.append($('<td>').text(layer_subscription.type_str))
                    row.append($('<td>').text(layer_subscription.workspace_str))
                    row.append($('<td class="text-center">').append(layer_subscription.enabled ? '<img class="yes-no-icon" src="/static/admin/img/icon-yes.svg" alt="True">' : '<img class="yes-no-icon" src="/static/admin/img/icon-no.svg" alt="False">'))
                    row.append($('<td>').text(layer_subscription.updated_at))
                    row.append($('<td>').text(layer_subscription.assigned_to_name))
                    
                    // Buttons
                    let td_for_buttons = $('<td class="text-end">')
                    let button_view = $('<button class="btn btn-primary btn-sm mx-1" id="subscription-tbody-row-' + layer_subscription.id + '-view">View</button>')
                    let button_delete = $('<button class="btn btn-danger btn-sm" id="subscription-tbody-row-' + layer_subscription.id + '-delete">Delete</button>')
                    button_view.click(()=>window.location.href = '/layer/subscriptions/' + layer_subscription.id + '/')
                    button_delete.click(()=>kblayersubscription.delete_subscription(layer_subscription))
                    td_for_buttons.append(button_view)
                    td_for_buttons.append(button_delete)
                    row.append(td_for_buttons)
                    $('#subscription-tbody').append(row)
                }

                common_pagination.init(response.count, params, kblayersubscription.get_layer_subscription, $('#subscription-navi'));
            },
            error: function (error){
                common_entity_modal.show_alert("An error occured while getting layer subscription.");
                console.log(error)
            }
        });
    },
    get_workspace: function(callback){
        $.ajax({
            url: kblayersubscription.var.publish_workspace_url,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                if(!response || !response.results){
                    common_entity_modal.show_alert("Error occured while getting workspaces");
                    return;
                }
                for(let i in response.results){
                    kblayersubscription.var.workspace_map[response.results[i].id] = response.results[i].name; 
                }
                $('#layer-subscription-workspace').empty();
                $('#layer-subscription-workspace').append($('<option>', {
                    value: null,
                    text: "All"
                }));
                for(let key in kblayersubscription.var.workspace_map){
                    let option=$('<option>', {
                        value: key,
                        text: kblayersubscription.var.workspace_map[key]
                    });
                    $('#layer-subscription-workspace').append(option);
                }
                if(callback){
                    callback();
                }
            },
            error: function (error){
                common_entity_modal.show_alert("An error occured while getting workspace.");
                console.log(error);
            }
        });
    },
    show_new_subscription_modal: function(){
        common_entity_modal.init("New Subscription", "submit");

        fields = {};
        fields.type = {id:common_entity_modal.add_field(label="Type", type="select", value=1, option_map=kblayersubscription.var.subscription_type_map)};    //publish workspace
        fields.workspace = {id:common_entity_modal.add_field(label="Workspace", type="select", value=null, option_map=kblayersubscription.var.workspace_map)};    //publish workspace
        fields.name = {id:common_entity_modal.add_field(label="Name", type="text")};
        fields.description = {id:common_entity_modal.add_field(label="Description", type="text_area")};
        fields.enabled = {id:common_entity_modal.add_field(label="Enabled", type="switch")};
        fields.url = {id:common_entity_modal.add_field(label="capabilities URL", type="text")};
        fields.host = {id:common_entity_modal.add_field(label="Host", type="text")};
        fields.port = {id:common_entity_modal.add_field(label="Port", type="number")};
        fields.database = {id:common_entity_modal.add_field(label="Database", type="text")};
        fields.schema = {id:common_entity_modal.add_field(label="Schema", type="text")};
        fields.username = {id:common_entity_modal.add_field(label="User Name(Optional)", type="text")};
        fields.userpassword = {id:common_entity_modal.add_field(label="User Password(Optional)", type="password")};
        fields.connection_timeout = {id:common_entity_modal.add_field(label="Connection Timeout(ms)", type="number", value=kblayersubscription.var.default_connection_timout)};
        fields.max_connections = {id:common_entity_modal.add_field(label="Max Concurrent Connections", type="number", value=kblayersubscription.var.default_max_concurrent_connections)};
        fields.min_connections = {id:common_entity_modal.add_field(label="Min Concurrent Connections", type="number", value=kblayersubscription.var.default_mim_concurrent_connections)};
        fields.read_timeout = {id:common_entity_modal.add_field(label="Read Timeout(ms)", type="number", value=kblayersubscription.var.default_read_timout)};
        fields.fetch_size = {id:common_entity_modal.add_field(label="Fetch Size", type="number", value=kblayersubscription.var.default_fetch_size)};
        fields.ssl_mode = {id:common_entity_modal.add_field(label="SSL Mode", type="select", value="allow", option_map=kblayersubscription.var.ssl_mode_map)};

        set_entities = function(type){
            for(let key in fields){
                common_entity_modal.hide_entity(fields[key].id);
            }
            
            const required_fields = kblayersubscription.var.required_fields[type];
            for(let i in required_fields){
                common_entity_modal.show_entity(fields[required_fields[i]].id);
            }

            const optional_fields = kblayersubscription.var.optional_fields;
            for(let i in optional_fields){
                common_entity_modal.show_entity(fields[optional_fields[i]].id);
            }
        }
        
        set_entities(1); //WMS

        // change feilds by type change
        $('#'+fields.type.id).change(function(){
            const type = $('#'+fields.type.id).val();
            set_entities(type);
        });

        common_entity_modal.add_callbacks(
                submit_callback=(success_callback, error_callback)=> kblayersubscription.create_subscription(success_callback, error_callback, fields),
                success_callback=()=>table.refresh(kblayersubscription.get_layer_subscription));
        common_entity_modal.show();
    },
    create_subscription: function(success_callback, error_callback, fields){
        const type = $('#'+fields.type.id).val();
        var subscription_data = {};
        required_fields = kblayersubscription.var.required_fields[type];

        for(let i in required_fields){
            const key = required_fields[i];
            if(key == 'enabled'){
                subscription_data[key] = $('#'+fields[key].id).prop('checked');
            } else {
                subscription_data[key] = utils.validate_empty_input(common_entity_modal.get_label(fields[key].id), $('#'+fields[key].id).val());
            }
        }
        optional_fields = kblayersubscription.var.optional_fields;
        for(let i in optional_fields){
            const key = optional_fields[i];
            const val = $('#'+fields[key].id).val();
            if(val){
                subscription_data[key] = val;
            }
        }
        
        var url = kblayersubscription.var.layersubscription_data_url;
        var method = 'POST';

        // call POST API
        $.ajax({
            url: url,
            method: method,
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            data: JSON.stringify(subscription_data),
            success: success_callback,
            error: error_callback
        });
    },
    delete_subscription: function(subscription){
        let delete_subscription_callback = function(success_callback, error_callback){
            var url = kblayersubscription.var.layersubscription_data_url+subscription.id+"/";
            var method = 'DELETE';

            // call POST API
            $.ajax({
                url: url,
                method: method,
                dataType: 'json',
                contentType: 'application/json',
                headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
                success: success_callback,
                error: error_callback
            });
        }

        common_entity_modal.init("Delete Subscription", "delete");
        common_entity_modal.add_field(label="ID", type="number", value=subscription.id);
        common_entity_modal.add_field(label="Name", type="text", value=subscription.name);
        common_entity_modal.add_field(label="Type", type="text", value=subscription.type_str);
        common_entity_modal.add_callbacks(submit_callback=(success_callback, error_callback)=> 
                                    delete_subscription_callback(success_callback, error_callback),
                                    success_callback=()=>table.refresh(kblayersubscription.get_layer_subscription));
        common_entity_modal.show();
    },

    // *** View page *** //
    init_subscription_item: function(){
        $("#subscription-lock").click(() => kblayersubscription.change_subscription_status('lock'));
        $("#subscription-unlock").click(() => kblayersubscription.change_subscription_status('unlock'));
        $("#subscription-assigned-to-btn").click(() =>kblayersubscription.set_assigned_to());
        
        $("#log_actions_show").click(kblayersubscription.show_action_log);
        $("#log_communication_show").click(kblayersubscription.show_communication_log);
        $("#log_communication_add").click(kblayersubscription.add_communication_log);

        // Display Modal to create a new catalogue entry
        $("#subscription-add-layer-btn").click(() => {
            $('#subscription_add_edit_modal_title').text('Create Catalogue Entry')
            $('#layer_name_to_be_added').val('')
            $('#catalogue_entry_name_to_be_added').val('')
            $('#catalogue_entry_id').val('')
            $('#add_edit_catalogue_entry_btn').text('Create Catalogue Entry')
            $('#add_edit_catalogue_entry_error').text('').hide()
            kblayersubscription.checkCatalogueEntryInputs();
            $('#SubscriptionAddLayerModal').modal('show');
        })
        // Add/Update layer
        $('#add_edit_catalogue_entry_btn').click(()=>{
            let layer_name = $('#layer_name_to_be_added').val()
            let catalogue_entry_name_to_be_added = $('#catalogue_entry_name_to_be_added').val()
            let catalogue_entry_id = $('#catalogue_entry_id').val()
            kblayersubscription.create_update_mapping(layer_name, catalogue_entry_name_to_be_added, catalogue_entry_id)
        })

        $('#catalogue_entry_name_to_be_added').on('input', kblayersubscription.checkCatalogueEntryInputs);
        $('#layer_name_to_be_added').on('input', kblayersubscription.checkCatalogueEntryInputs);

        $("#subscription-btn-save").click(function() {
            kblayersubscription.save_subscription('save');
        });
        $('#update_wms_source_list_btn').click(kblayersubscription.updateSourceList)
        $('#update_wfs_source_list_btn').click(kblayersubscription.updateSourceList)
        $('#update_postgis_source_list_btn').click(kblayersubscription.updateSourceList)
        $('#subscription_check_connection_btn').click(kblayersubscription.check_connection);

        if([1,2].includes(+$('#subscription-type-num').val())){
            // WMS, WFS
            kblayersubscription.get_mappings();
        }else{
            // PostGIS
            kblayersubscription.get_mappings();
            kblayersubscription.get_custom_query_info();
        }

        if($('#subscription_enabled').val() == 'True'){
            $('#subscription-enabled').prop('checked', true);
        }
        $('#subscription-dbtable-table-custom-add').click(function(){
            kblayersubscription.show_custom_query_modal();
        });

        kblayersubscription.retrieve_communication_types();
        kblayersubscription.checkCatalogueEntryInputs();
        kblayersubscription.check_connection();
    },
    check_connection: async() => {
        const $button = $(this);
        const $spinner = $('#subscription_check_connection_spinner')

        $button.prop('disabled', true);
        $spinner.show()
        try {
            await kblayersubscription.perform_check_connection();
        } finally {
            $button.prop('disabled', false);
            $spinner.hide()
        }
    },
    updateSourceList: async () => {
        const $button = $(this);
        const $spinner = $('#update_source_list_spinner')

        $button.prop('disabled', true);
        $spinner.show()
        
        try {
            await kblayersubscription.get_mappings(true);
        } finally {
            $button.prop('disabled', false);
            $spinner.hide()
        }
    },
    checkCatalogueEntryInputs: function() {
        console.log('in checkInputs()')
        const catalogueEntryName = $('#catalogue_entry_name_to_be_added').val();
        const layerName = $('#layer_name_to_be_added').val();
        if (catalogueEntryName && layerName) {
            $('#add_edit_catalogue_entry_btn').prop('disabled', false);
        } else {
            $('#add_edit_catalogue_entry_btn').prop('disabled', true);
        }
    },
    change_subscription_status: function(status){
        $('#loadingOverlay').fadeIn();

        var status_url = "lock";
        if (status == 'unlock') {
            status_url = 'unlock';
        }

        var subscription_id = $('#subscription_id').val();
        var csrf_token = $("#csrfmiddlewaretoken").val();

        if (subscription_id == null || subscription_id == ''){
            $('#loadingOverlay').fadeOut();
            return
        }

        $.ajax({
            url: kblayersubscription.var.subscription_save_url+subscription_id+"/"+status_url+"/",
            type: 'POST',
            headers: {'X-CSRFToken' : csrf_token},
            contentType: 'application/json',
            success: function (response) {
                window.location = "/layer/subscriptions/"+subscription_id;
            },
            error: function (error) {
                common_entity_modal.show_alert("ERROR Changing Status");
            },
            complete: function(xhr, status){
                $('#loadingOverlay').fadeOut();
            }
        });
    },
    set_assigned_to: function(){

        var assignedto = $('#subscription-assigned-to').val();
        var subscription_id = $('#subscription_id').val();
        var csrf_token = $("#csrfmiddlewaretoken").val();

        if (assignedto == null || assignedto.length == 0 || assignedto === ''){
            common_entity_modal.show_alert("Please select an assigned-to person first.");
            return
        }

        $('#loadingOverlay').fadeIn();
        $.ajax({
            url: kblayersubscription.var.subscription_save_url+subscription_id+"/assign/"+assignedto+"/",
            type: 'POST',
            headers: {'X-CSRFToken' : csrf_token},
            contentType: 'application/json',
            success: function (response) {
                window.location = "/layer/subscriptions/"+subscription_id;
            },
            error: function (error) {
                common_entity_modal.show_alert("ERROR Setting assigned person.");
            },
            complete: function(xhr, status){
                $('#loadingOverlay').fadeOut();
            }
        });
    },
    show_action_log: function(){
        common_entity_modal.init("Action log", "info");
        common_entity_modal.init_talbe();
        let thead = common_entity_modal.get_thead();
        table.set_thead(thead, {Who:3, What:5, When:4});
        common_entity_modal.get_limit().change(()=>kblayersubscription.get_action_log());
        common_entity_modal.get_search().keyup((event)=>{
            if (event.which === 13 || event.keyCode === 13){
                event.preventDefault();
                kblayersubscription.get_action_log()
            }
        });
        common_entity_modal.show();

        kblayersubscription.get_action_log();
    },
    get_action_log: function(params_str){
        if(!params_str){
            params = {
                limit:  common_entity_modal.get_limit().val(),
                search: common_entity_modal.get_search().val(),
            }

            params_str = utils.make_query_params(params);
        }
    
        var subscription_id = $('#subscription_id').val();
        $.ajax({
            url: kblayersubscription.var.subscription_save_url+subscription_id+"/logs/actions/?"+params_str,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                if(!response || !response.results){
                    table.message_tbody(common_entity_modal.get_tbody(), "No results found");
                    return;
                }
                for(let i in response.results){
                    response.results[i]['when'] = utils.convert_datetime_format(response.results[i].when, kblayersubscription.var.subscription_table_date_format); 
                }
                table.set_tbody(common_entity_modal.get_tbody(), response.results, [{username:"text"}, {what:'text'}, {when:'text'}]);
                common_pagination.init(response.count, params, kblayersubscription.get_action_log, common_entity_modal.get_page_navi());
            },
            error: function (error){
                common_entity_modal.show_error_modal(error);
            }
        });
    },
    show_communication_log: function(){
        common_entity_modal.init("Communication log", "info");
        common_entity_modal.init_talbe();
        let thead = common_entity_modal.get_thead();
        table.set_thead(thead, {User:2, To:2, Cc:2, From:2, Subject:2, Text:2});
        common_entity_modal.get_limit().change(()=>kblayersubscription.get_communication_log());
        common_entity_modal.get_search().keyup((event)=>{
            if (event.which === 13 || event.keyCode === 13){
                event.preventDefault();
                kblayersubscription.get_communication_log()
            }
        });
        common_entity_modal.show();

        kblayersubscription.get_communication_log();
    },
    get_communication_log: function(params_str){
        if(!params_str){
            params = {
                limit:  common_entity_modal.get_limit().val(),
                search: common_entity_modal.get_search().val(),
            }

            params_str = utils.make_query_params(params);
        }
    
        var subscription_id = $('#subscription_id').val();
        $.ajax({
            url: kblayersubscription.var.subscription_save_url+subscription_id+"/logs/communications/?"+params_str,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                if(!response || !response.results){
                    table.message_tbody(common_entity_modal.get_tbody(), "No results found");
                    return;
                }
                for(let i in response.results){
                    response.results[i]['created_at'] = utils.convert_datetime_format(response.results[i].created_at, kblayersubscription.var.subscription_table_date_format); 
                }
                table.set_tbody(common_entity_modal.get_tbody(), response.results, 
                                [{username:"text"}, {to:'text'}, {cc:'text'}, {from:'text'}, {subject:'text'}, {text:'text'}]);
                common_pagination.init(response.count, params, kblayersubscription.get_communication_log, common_entity_modal.get_page_navi());
            },
            error: function (error){
                common_entity_modal.show_error_modal(error);
            }
        });
    },
    add_communication_log: function(){
        common_entity_modal.init("Add New Communication log", "submit");
        let type_id = common_entity_modal.add_field(label="Communication Type", type="select", value=null, option_map=kblayersubscription.var.communication_type);
        let to_id = common_entity_modal.add_field(label="To", type="text");
        let cc_id = common_entity_modal.add_field(label="Cc", type="text");
        let from_id = common_entity_modal.add_field(label="From", type="text");
        let subject_id = common_entity_modal.add_field(label="Subject", type="text");
        let text_id = common_entity_modal.add_field(label="Text", type="text_area");

        common_entity_modal.add_callbacks(submit_callback=(success_callback, error_callback)=> 
                                        kblayersubscription.create_communication_log(
                                            success_callback, error_callback, type_id, 
                                            to_id, cc_id, from_id, subject_id, text_id));
        common_entity_modal.show();
    },
    create_communication_log: function(success_callback, error_callback, type_id, to_id, cc_id, from_id, subject_id, text_id){
        // get & validation check
        const type = utils.validate_empty_input('type', $('#'+type_id).val());
        const to = utils.validate_empty_input('to', $('#'+to_id).val());
        const cc = utils.validate_empty_input('cc', $('#'+cc_id).val());
        const from = utils.validate_empty_input('from', $('#'+from_id).val());
        const subject = utils.validate_empty_input('subject', $('#'+subject_id).val());
        const text = utils.validate_empty_input('text', $('#'+text_id).val());
        
        // make data body
        var communication_log_data = {
            type:type,
            to:to,
            cc:cc,
            from:from,
            subject:subject,
            text:text,
            user:$('#current-user').val(),
        };
        
        var subscription_id = $('#subscription_id').val();
        var url = kblayersubscription.var.subscription_save_url+subscription_id+"/logs/communications/";
        var method = 'POST';

        // call POST API
        $.ajax({
            url: url,
            method: method,
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            data: JSON.stringify(communication_log_data),
            success: success_callback,
            error: error_callback
        });
    },
    save_subscription: function(mode){
        const type = $('#subscription-type-num').val();
        
        // make data body
        var update_subscription_data = {};
        const fields = kblayersubscription.var.required_fields;

        for( let i in fields[type] ){
            const key = fields[type][i];
            if( key == 'type'){
                continue;
            }
            const id = "subscription-"+key.replaceAll('_', '-');
            if(key == 'enabled'){
                update_subscription_data[key] = $('#'+id).prop('checked');
            } else {
                try{
                    update_subscription_data[key] = utils.validate_empty_input(key, $('#'+id).val());
                } catch (error){
                    common_entity_modal.show_alert(error);
                    return;
                }
            }
        }
        
        let optional_fields = kblayersubscription.var.optional_fields
        for( let i in optional_fields ){
            const key = optional_fields[i];
            const id = "subscription-"+key.replaceAll('_', '-');
            const val = $('#'+id).val();
            if(val !== undefined && val !== null){
                update_subscription_data[key] = val;
            }
        }

        var subscription_id = $('#subscription_id').val();
        var url = kblayersubscription.var.subscription_save_url+subscription_id+"/";
        var method = 'PUT';

        // call POST API
        $.ajax({
            url: url,
            method: method,
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            data: JSON.stringify(update_subscription_data),
            success: function (response) {
                if(mode == "save"){
                    location.reload();
                } else if (mode == "save-and-exit"){
                    window.location.href = "/layer/subscriptions/";
                }
            },
            error: error => {
                common_entity_modal.show_alert("An error occured while updating a subscription.");
                console.log(error);
            }
        });
    },
    get_mappings: async function(force_to_query=false){
        try{
            const [source_layers, catalogue_entries] = await Promise.all([
                kblayersubscription.get_mapping_source(force_to_query),
                kblayersubscription.get_mapping_info()
            ]);

            kblayersubscription.var.source_layers = source_layers
            kblayersubscription.construct_catalogue_entries_table(catalogue_entries);  // This table is displayed on the page.
            kblayersubscription.construct_source_layers_table(catalogue_entries);  // This is displayed in the add/edit modal
        } catch (error){
            console.error('Error', error)
        }
    },
    isLocked: function(value) {
        if (typeof value === 'boolean') {
            return value;
        }
        if (typeof value === 'string') {
            return value.toLowerCase() !== 'false';
        }
        return true;
    },
    getTitleByMappingName: (mappingName) => {
        for (let layer of kblayersubscription.var.source_layers) {
            if (layer.name === mappingName) {
                return layer.title;
            }
        }
        return '';
    },
    construct_catalogue_entries_table: function(catalogue_entries){
        const table = $('#catalogue-entries-table')
        let is_locked = $('#subscription_obj_is_locked').val()

        if ($.fn.DataTable.isDataTable(table)) {
            table.DataTable().destroy();
        }

        table.empty();

        let columns = [
            { 
                title: 'ID',
                data: 'id',
                className: 'text-start',
                render: (data, type, row) => {
                    return type === 'display' ? `<a href="/catalogue/entries/${data}/details/" style="text-decoration: none;">CE${data}</a>` : data;
                },
                type: 'num'
            },
            { 
                title: 'Catalogue Entry',
                data: 'name'
            },
            { 
                title: 'Mapping Name',
                data: 'mapping_name',
                render: (data, type, row) => {
                    if (type === 'display') {
                        const sourceLayerNames = new Set(kblayersubscription.var.source_layers.map(layer => layer.name));
                        const isMappingNameInSourceLayers = sourceLayerNames.has(data);
                        return `<span style="${isMappingNameInSourceLayers ? '' : 'background-color: #ffc107;'}" title="This mapping name does not match any layer name on the server.">${data}</span>`;
                    }
                    return data;
                }
            }
        ];
        if([1, 2].includes(+$('#subscription-type-num').val())){
            // When WMS/WFS, display the Title column in the table
            columns.push({
                title: 'Title',
                data: null,
                // className: "col-2 text-end",
                render: (data, type, row) => {
                    return kblayersubscription.getTitleByMappingName(row.mapping_name)
                },
            })
        }

        if(!kblayersubscription.isLocked(is_locked) && $('#has_edit_access').val() === "True"){
            // When the page is not locked, we want to show the buttons
            columns.push({
                title: 'Action',
                data: null,
                className: "col-2 text-end",
                render: (data) => {
                    return `<button class='btn btn-primary btn-sm select-existing-layer-btn' 
                        data-catalogue-entry-id="${data.id}" 
                        data-mapping-name="${data.mapping_name}" 
                        data-catalogue-entry-name="${data.name}">Edit</button>`;
                },
                orderable: false
            })
        }
    
        table.DataTable({
            destroy: true,
            data: catalogue_entries.filter(entry => !entry.is_custom_query),
            columns: columns,
            order: [[0, 'asc']],
            responsive: true,
            deferRender: true,
            headerCallback: function(thead) {
                $(thead).addClass('table-dark');
            }
        });

        // Step 4: Add event listener for Select buttons
        $(document).on('click', '.select-existing-layer-btn', function() {
            // Step 5: Get the data-name value
            const layerName = $(this).data('mapping-name');
            const catalogueEntryName = $(this).data('catalogue-entry-name');
            const catalogueEntryId = $(this).data('catalogue-entry-id');

            // Step 6: Update the values
            $('#subscription_add_edit_modal_title').text('Update Catalogue Entry')
            $('#add_edit_catalogue_entry_btn').text('Update Catalogue Entry')
            $('#layer_name_to_be_added').val(layerName);  // Somehow doesn't work !!!
            $('#catalogue_entry_name_to_be_added').val(catalogueEntryName);
            $('#catalogue_entry_id').val(catalogueEntryId);
            $('#add_edit_catalogue_entry_error').text('').hide()

            kblayersubscription.checkCatalogueEntryInputs();
            $('#SubscriptionAddLayerModal').modal('show');
        });
    },
    construct_source_layers_table: function(catalogue_entries){
        /* Construct the table in a add/edit catalogue entry modal */
        const tableBody = $('#source-layers-table tbody');
        tableBody.empty(); // Clear existing rows
    
        // Step 1: Convert catalogue_entries mapping_names to a Set for fast lookup
        const catalogueMappingNames = new Set(catalogue_entries.map(entry => entry.mapping_name));

        // Step 2: Iterate over catalogue_entries and append rows to the table
        kblayersubscription.var.source_layers.forEach(layer => {
            if (!catalogueMappingNames.has(layer.name)) {
                const row = `<tr>
                    <td>${layer.name}</td>
                    <td>${layer.title}</td>
                    <td><button class='btn btn-primary btn-sm select-layer-btn' data-name="${layer.name}">Select</button></td>
                </tr>`;
                tableBody.append(row);
            }
        });

        // Step 3: Initialize DataTable
        $('#source-layers-table').DataTable();

        // Step 4: Add event listener for Select buttons
        $(document).on('click', '.select-layer-btn', function() {
            // Step 5: Get the data-name value
            const layerName = $(this).data('name');

            // Step 6: Update the value of the element with id="layer_name_to_be_added"
            $('#layer_name_to_be_added').val(layerName).trigger('input');
        });
    },
    perform_check_connection: function(){
        $("#subscription_check_connection_results").empty();
        $("#subscription_check_connection_spinner").show();
        $("#subscription_check_connection_btn").prop("disabled", true);

        // call GET API
        $.ajax({
            url: kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/check_connection/",
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            success: (response, status, xhr) => {
                // triggered when the server responds with a status code in the range of 200 to 299 (inclusive) or 304.
                if (xhr.status === 200) {
                    $("#subscription_check_connection_results").html(
                        '<div class="mt-2">' +
                        '<span class="text-success"><img class="yes-no-icon" src="/static/admin/img/icon-yes.svg" alt="True"></span> ' +
                        '<span>Connection is successful.</span>' +
                        '</div>'
                    );
                } else {
                    let message = response.results || "Unknown error occurred.";
                    $("#subscription_check_connection_results").html(
                        '<div class="mt-2">' +
                        '<span class="text-danger"><img class="yes-no-icon" src="/static/admin/img/icon-no.svg" alt="True"></span> ' +
                        '<span>Connection failed: ' + message + '</span>' +
                        '</div>'
                    );
                }
            },
            error: (xhr, status, error)=> {
                // executed when the server responds with a status code outside the 200-299 range, such as 400 (Bad Request), 404 (Not Found), or 500 (Internal Server Error). 
                let errorMessage = "Unknown error occurred.";
                if (xhr.responseJSON) {
                    if (xhr.responseJSON.error) {
                        errorMessage = xhr.responseJSON.error;
                    } else if (xhr.responseJSON.results) {
                        errorMessage = xhr.responseJSON.results;
                    }
                }
                $("#subscription_check_connection_results").html(
                    '<div class="mt-2">' +
                    '<span class="text-danger"><img class="yes-no-icon" src="/static/admin/img/icon-no.svg" alt="True"></span> ' +
                    '<span>Connection failed: ' + errorMessage + '</span>' +
                    '</div>'
                );
            },
            complete: () => {
                $("#subscription_check_connection_spinner").hide();
                $("#subscription_check_connection_btn").prop("disabled", false);
            }
        });
    },
    get_mapping_source: function(force_to_query=false){
        return new Promise((resolve, reject) => {
            let url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/mapping/source";
            let method = 'GET';

            // call GET API
            $.ajax({
                url: url,
                method: method,
                dataType: 'json',
                contentType: 'application/json',
                headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
                data: { force_to_query: force_to_query },
                success: (response) => {
                    if(!response || !response.results){
                        resolve([]);
                        return
                    }

                    resolve(response.results)
                },
                error: (error)=> {
                    reject(error)
                },
            });
        })
    },
    get_mapping_info: function(){
        return new Promise((resolve, reject) => {
            let url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/mapping/";
            let method = 'GET';

            // call GET API
            $.ajax({
                url: url,
                method: method,
                dataType: 'json',
                contentType: 'application/json',
                headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
                success: (response) => {
                    if(!response || !response.results){
                        // table.message_tbody(tbody, "No results found");
                        resolve({})
                        return;
                    }
                    resolve(response.results)
                },
                error: (error)=> {
                    reject(error)
                },
            });
        })
    },
    create_update_mapping: function(layer_name, catalogue_entry_name, catalogue_entry_id){
        // call create layer api via ajax
        mapping_data = {
            'name': catalogue_entry_name,
            'mapping_name': layer_name,
        }

        url = ''
        method = ''
        if (catalogue_entry_id){
            url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/mapping/" + catalogue_entry_id + "/";
            method = 'PUT';
        } else {
            url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/mapping/";
            method = 'POST';
        }

        // call POST API
        $.ajax({
            url: url,
            method: method,
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            data:  JSON.stringify(mapping_data),
            success: async function(response) {
                const catalogue_entries = await kblayersubscription.get_mapping_info();
                $('#SubscriptionAddLayerModal').modal('hide');
                kblayersubscription.construct_catalogue_entries_table(catalogue_entries)
                kblayersubscription.construct_source_layers_table(catalogue_entries)
            },
            error: function(xhr, status, error) {
                var errorMessages = [];
                if (xhr.responseJSON) {
                    for (var key in xhr.responseJSON) {
                        if (xhr.responseJSON.hasOwnProperty(key)) {
                            errorMessages.push(key + ": " + xhr.responseJSON[key]);
                        }
                    }
                } else {
                    errorMessages.push("An unknown error occurred.");
                }
                $('#add_edit_catalogue_entry_error').text(errorMessages.join(", ")).show();
            }
        });
    },
    retrieve_communication_types: function(){
        $.ajax({
            url: kblayersubscription.var.log_communication_type_url,
            type: 'GET',
            contentType: 'application/json',
            success: (response) => {
                if(!response){
                    common_entity_modal.show_alert("An error occured while getting retrieve communication types.");
                    return;    
                }
                var communication_type = {};
                for(let i in response.results){
                    const type = response.results[i];
                    communication_type[type.id] = type.label;
                }
                kblayersubscription.var.communication_type = communication_type;
            },
            error: (error)=> {
                common_entity_modal.show_alert("An error occured while getting retrieve communication types.");
            },
        });
    },
    get_custom_query_info: function(){
        console.log('in get_custom_query_info()')
        let url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/query/";
        let method = 'GET';

        let thead = $("#subscription-custom-query-table-thead");
        let tbody = $("#subscription-custom-query-table-tbody");
        // let title = "Native Layer";

        // call GET API
        $.ajax({
            url: url,
            method: method,
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            success: (response) => {
                thead.empty();
                let tr = $('<tr>');
                tr.append($('<th>').attr('class', 'col-1').text("ID"))
                tr.append($('<th>').attr('class', 'col-5').text("Catalogue Entry"))
                tr.append($('<th>').attr('class', 'col-2').text("Frequency"))
                tr.append($('<th>').attr('class', 'col-2').text("Force Run"))
                tr.append($('<th>').attr('class', 'col-2 text-end').text("Action"))
                thead.append(tr);

                if(!response || !response.results.length){
                    tbody.html("<tr><td colspan='4' class='text-center'>No results found</td></tr>");
                    return;
                }

                tbody.empty();
                for(let catalogue_entry of response.results){
                    let row = $('<tr>');
                    row.append($('<td>').append($('<a href="/catalogue/entries/' + catalogue_entry.id + '/details/" style="text-decoration: none;">').text(`CE${catalogue_entry.id}`)))
                    row.append($('<td>').html(`${catalogue_entry.name}`))
                    let typeLabels = catalogue_entry.frequencies.map(frequency => frequency.type_label).join('<br>');
                    let td = $('<td>').html(typeLabels);
                    row.append(td);
                    row.append($('<td>').append(catalogue_entry.force_run_postgres_scanner ? '<img class="yes-no-icon" src="/static/admin/img/icon-yes.svg" alt="True">' : '<img class="yes-no-icon" src="/static/admin/img/icon-no.svg" alt="False">'))

                    // Buttons
                    let td_for_buttons = $('<td class="text-end">')
                    if($('#has_edit_access').val() == "True"){
                        let button_edit = $('<button class="btn btn-primary btn-sm mx-1" id="subscription-custom-query-table-tbody-row-' + catalogue_entry.id + '-history">Edit</button>')
                        let button_delete = $('<button class="btn btn-danger btn-sm" id="subscription-custom-query-table-tbody-row-' + catalogue_entry.id + '-delete">Delete</button>')
                        button_edit.click(()=>kblayersubscription.show_custom_query_modal(catalogue_entry))
                        button_delete.click(()=>kblayersubscription.delete_custom_query(catalogue_entry))
                        td_for_buttons.append(button_edit)
                        td_for_buttons.append(button_delete)
                    }
                    row.append(td_for_buttons)
                    tbody.append(row);
                }
            },
            error: (error)=> {
                tbody.html("<tr><td colspan='4' class='text-center'>" + message + "</td></tr>");
                common_entity_modal.show_alert("An error occured while getting mappings.");
            },
        });
    },
    get_custom_query_info_not_working: function() {
        console.log('in get_custom_query_info()');
        let url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/query/";
        
        // Destroy existing DataTable if it exists
        let table = $('#subscription-custom-query-table').DataTable();
        if (table) {
            table.destroy();
        }
    
        // Initialize DataTable with complete configuration
        $('#subscription-custom-query-table').DataTable({
            processing: true,  // Show loading indicator
            serverSide: false, // Not using server-side processing
            ajax: {
                url: url,
                method: 'GET',
                headers: {'X-CSRFToken': $("#csrfmiddlewaretoken").val()},
                dataSrc: function(response) {
                    return response.results || [];
                }
            },
            headerCallback: function(thead, data, start, end, display) {
                $(thead).addClass('table-dark');
            },
            columns: [
                {
                    title: "ID",
                    data: "id",
                    className: "col-1",
                    render: function(data, type, row) {
                        return '<a href="/catalogue/entries/' + data + '/details/" style="text-decoration: none;">CE' + data + '</a>';
                    },
                    type: 'num'
                },
                {
                    title: "Catalogue Entry",
                    data: "name",
                    // className: "col-5"
                },
                {
                    title: "Frequency",
                    data: "frequencies",
                    className: "col-2",
                    render: function(data, type, row) {
                        return data.map(frequency => frequency.type_label).join('<br>');
                    }
                },
                {
                    title: "Force Run",
                    data: "force_run_postgres_scanner",
                    className: "col-2",
                    render: function(data, type, row) {
                        return data ? 
                            '<img class="yes-no-icon" src="/static/admin/img/icon-yes.svg" alt="True">' : 
                            '<img class="yes-no-icon" src="/static/admin/img/icon-no.svg" alt="False">';
                    }
                },
                {
                    title: "Action",
                    data: null,
                    className: "col-2 text-end",
                    orderable: false,
                    render: function(data, type, row) {
                        if (type === 'display' && $('#has_edit_access').val() === "True") {
                            return '<div class="btn-group">' +
                                   '<button class="btn btn-primary btn-sm mx-1 btn-edit" ' +
                                   'data-entry-id="' + row.id + '">Edit</button>' +
                                   '<button class="btn btn-danger btn-sm btn-delete" ' +
                                   'data-entry-id="' + row.id + '">Delete</button>' +
                                   '</div>';
                        }
                        return '';
                    }
                }
            ],
            pageLength: 10,
            lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
            order: [[0, 'asc']],
            responsive: true,
            drawCallback: function(settings) {
                // Any additional setup after table draw
                const table = this;
            
                $('#subscription-dbtable-custom-table table').on('click', 'button.btn-edit', function(e) {
                    e.preventDefault();
                    const entryId = $(this).data('entry-id');
                    const rowData = table.api().row($(this).closest('tr')).data();
                    kblayersubscription.show_custom_query_modal(rowData);
                });
                
                $('#subscription-dbtable-custom-table table').on('click', 'button.btn-delete', function(e) {
                    e.preventDefault();
                    const entryId = $(this).data('entry-id');
                    const rowData = table.api().row($(this).closest('tr')).data();
                    kblayersubscription.delete_custom_query(rowData);
                });
            }
        }).on('error.dt', function(e, settings, techNote, message) {
            $('#subscription-custom-query-table-tbody').html("<tr><td colspan='5' class='text-center'>An error occurred while getting mappings.</td></tr>");
            common_entity_modal.show_alert("An error occurred while getting mappings.");
        });
    },
    convert_custom_query: function(catalogue_entry){
        var url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/convert-query/" + catalogue_entry.id + "/";
        $.ajax({
            url: url,
            method: 'POST',
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            success: (response) => {
                FeedbackModal.showFeedback(response.message, true);
            },
            error: (xhr, status, error) => {
                FeedbackModal.showFeedback('Error: ' + xhr.responseJSON.message, false);
            }
        })
    },
    show_custom_query_modal: function(prev){
        //options
        const frequecy_options = {1:'Every Minutes', 2:'Every Hours', 3:'Daily', 4:'Weekly', 5:'Monthly'};

        common_entity_modal.init("Add Custom Table Layer", type="submit");
        const name_id = common_entity_modal.add_field("Catalogue Entry Name", "text", prev ? prev.name : null);
        // const description_id = common_entity_modal.add_field("Description", "text", prev ? prev.description : null);
        const sql_query_id = common_entity_modal.add_field("SQL Query", "text_area", prev ? prev.sql_query : null);
        
        // Frequency
        let frequency_type = (prev && prev.frequencies && prev.frequencies.length > 0) ? prev.frequencies[0].type : null;
        const frequency_id = common_entity_modal.add_field("Frequency", "select", frequency_type, frequecy_options);
        const freq_option_ids = [];
        let div = common_entity_modal.maker.div();
        common_entity_modal.add_div("Frequency Options", div);
        const add_freq_btn_id = common_entity_modal.add_field("Add Frequency", "button", null, null, true);

        // Force run postgres scanner
        $('#common-entity-modal-content').append($('<br>'))
        common_entity_modal.add_field(label="Force Run Postgres Scanner", type="switch", prev ? prev.force_run_postgres_scanner : false)

        if(prev && prev.frequencies && prev.frequencies.length > 0){
            for(let i in prev.frequencies){
                kblayersubscription.create_freq_option(div, prev.frequencies[i].type, prev.frequencies[i], freq_option_ids, div.children().length);
            }
            if(frequency_type != 1 && frequency_type != 2){
                $('#'+add_freq_btn_id).prop("disabled", false);
            }
        }
        
        $('#'+frequency_id).change(function(){
            frequency_type = $('#'+frequency_id).val();
            freq_option_ids.splice(0, freq_option_ids.length);
            $('#'+add_freq_btn_id).prop("disabled", false);
            div.empty();
        });
        
        $('#'+add_freq_btn_id).click(()=>{
            if(frequency_type == 1 || frequency_type == 2)
            $('#'+add_freq_btn_id).prop("disabled", true);
            div.append(kblayersubscription.create_freq_option(div, frequency_type, null, freq_option_ids, div.children().length));
        });

        // const ids = {name_id:name_id, description_id:description_id, sql_query_id:sql_query_id, frequency_id:frequency_id, freq_option_ids:freq_option_ids};
        const ids = {name_id:name_id, sql_query_id:sql_query_id, frequency_id:frequency_id, freq_option_ids:freq_option_ids};
        common_entity_modal.add_callbacks(
            submit_callback=(success_callback, error_callback)=> 
                kblayersubscription.write_custom_query(success_callback, error_callback, ids, prev),
            success_callback=kblayersubscription.get_custom_query_info);
        common_entity_modal.show();
    },
    create_freq_option: function(div, type, value, option_ids, seq){
        let row_div = common_entity_modal.maker.div();
        row_div.attr('class', 'row');
        row_div.attr('class', 'row');
        const ids = {};
        const labels_fields=[];

        const add_element = function(element, col=1, align_right=false){
            const div = common_entity_modal.maker.div();
            div.attr('class', 'col-'+col);
            if(align_right)
                div.attr('class', div.attr('class') + ' text_right');
            div.append(element);
            row_div.append(div);
            return element;
        }

        const set_min_max = function(number_input, min, max){
            number_input.on('input', function() {
                var val = $(this).val();
                if (val == "") return;
                else if (val < min) $(this).val(min);
                else if (isNaN(val) || val > max) $(this).val(max);
            });
        }
        if(type == 1){ //every_minutes
            const label = add_element($('<label>').text("Every"));
            const minutes_input = add_element(common_entity_modal.maker.number("minutes", value ? value.minutes : null));
            set_min_max(minutes_input, 1, 60);
            add_element($('<label>').text("Minutes"));
            labels_fields.push({label:label, field:minutes_input});
            ids.minutes = minutes_input.attr('id');
        }else if(type == 2){    //every_hours
            const label = add_element($('<label>').text("Every"));
            const hours_input = add_element(common_entity_modal.maker.number("hours", value ? value.hours : null));
            set_min_max(hours_input, 1, 24);
            add_element($('<label>').text("hours"));
            labels_fields.push({label:label, field:hours_input});
            ids.hours = hours_input.attr('id');
        }else if(type == 3){    //daily
            const label = add_element($('<label>').text("Every day(HH:MM)"),2);
            const hour_input = add_element(common_entity_modal.maker.number("hour", value ? value.hour : null));
            const minute_input = add_element(common_entity_modal.maker.number("minute", value ? value.minute : null));
            hour_input.attr('id', hour_input.attr('id')+'-'+seq);
            set_min_max(hour_input, 0, 23);
            minute_input.attr('id', minute_input.attr('id')+'-'+seq);
            set_min_max(minute_input, 0, 59);
            labels_fields.push({label:label, field:hour_input});
            labels_fields.push({label:label, field:minute_input});
            ids.hour = hour_input.attr('id');
            ids.minute = minute_input.attr('id');
        }else if(type == 4){    //weekly
            const label = add_element($('<label>').text("Day of the week: Hour: Minute)"),3);
            const day_options = {1:'Monday', 2:'Tuesday', 3:'Wednesday', 4:'Thurday', 5:'Friday', 6:'Saturday', 7:'Sunday'};
            const day_input = add_element(common_entity_modal.maker.select("day", value ? value.day : null, false, day_options), 2);
            const hour_input = add_element(common_entity_modal.maker.number("hour", value ? value.hour : null));
            const minute_input = add_element(common_entity_modal.maker.number("minute", value ? value.minute : null));
            day_input.attr('id', day_input.attr('id')+'-'+seq);
            hour_input.attr('id', hour_input.attr('id')+'-'+seq);
            set_min_max(hour_input, 0, 23);
            minute_input.attr('id', minute_input.attr('id')+'-'+seq);
            set_min_max(minute_input, 0, 59);
            labels_fields.push({label:label, field:day_input});
            labels_fields.push({label:label, field:hour_input});
            labels_fields.push({label:label, field:minute_input});
            ids.day = day_input.attr('id');
            ids.hour = hour_input.attr('id');
            ids.minute = minute_input.attr('id');
        }else if(type == 5){    //monthly
            const label = add_element($('<label>').text("Date: Hour: Minute"),3);
            const date_input = add_element(common_entity_modal.maker.number("date", value ? value.date : null));
            const hour_input = add_element(common_entity_modal.maker.number("hour", value ? value.hour : null));
            const minute_input = add_element(common_entity_modal.maker.number("minute", value ? value.minute : null));
            date_input.attr('id', date_input.attr('id')+'-'+seq);
            set_min_max(date_input, 1, 31);
            hour_input.attr('id', hour_input.attr('id')+'-'+seq);
            set_min_max(hour_input, 0, 23);
            minute_input.attr('id', minute_input.attr('id')+'-'+seq);
            set_min_max(minute_input, 0, 59);
            labels_fields.push({label:label, field:date_input});
            labels_fields.push({label:label, field:hour_input});
            labels_fields.push({label:label, field:minute_input});
            ids.date = date_input.attr('id');
            ids.hour = hour_input.attr('id');
            ids.minute = minute_input.attr('id');
        }

        const del_btn = common_entity_modal.maker.button("Delete", null, false);
        del_btn.click(()=>{
            row_div.remove();
            option_ids.splice(option_ids.indexOf(ids), 1);
        });
        add_element(del_btn, 2, true);
        labels_fields.push({label:del_btn, field:del_btn});
        common_entity_modal.add_labels_fields(labels_fields);
        
        option_ids.push(ids);   

        div.append(row_div);
        return row_div;
    },
    write_custom_query: function(success_callback, error_callback, ids, prev){
        var custom_query_data = {
            name : utils.validate_empty_input(common_entity_modal.get_label(ids.name_id), $('#'+ids.name_id).val()),
            // description : utils.validate_empty_input(common_entity_modal.get_label(ids.description_id), $('#'+ids.description_id).val()),
            description: '',
            sql_query : utils.validate_empty_input(common_entity_modal.get_label(ids.sql_query_id), $('#'+ids.sql_query_id).val()),
            frequency_type : utils.validate_empty_input(common_entity_modal.get_label(ids.frequency_id), +$('#'+ids.frequency_id).val()),
            force_run_postgres_scanner: $('#common-entity-modal-force-run-postgres-scanner').prop('checked')
        };
        if(ids.freq_option_ids == null || ids.freq_option_ids.length == 0){
            throw new Error("At least one frequency option is required");
        }
        const frequency_options = []
        for(let i in ids.freq_option_ids){
            const option = {};
            for(let key in ids.freq_option_ids[i]){
                option[key] = utils.validate_empty_input(key, $('#'+ids.freq_option_ids[i][key]).val());
            }
            frequency_options.push(option);
        }
        custom_query_data.frequency_options=frequency_options;

        var url = kblayersubscription.var.layersubscription_data_url + $('#subscription_id').val() + "/query/" + (prev ? prev.id+"/" : "");
        var method = prev ? 'PUT' : 'POST';

        // call POST API
        $.ajax({
            url: url,
            method: method,
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            data: JSON.stringify(custom_query_data),
            success: success_callback,
            error: error_callback
        });
    },
    delete_custom_query: function(query){
        let delete_query_callback = function(success_callback, error_callback){
            var url = kblayersubscription.var.layersubscription_data_url+$('#subscription_id').val()+"/delete-query/"+query.id+"/";
            var method = 'DELETE';

            // call POST API
            $.ajax({
                url: url,
                method: method,
                dataType: 'json',
                contentType: 'application/json',
                headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
                success: success_callback,
                error: error_callback
            });
        }

        common_entity_modal.init("Delete Subscription", "delete");
        common_entity_modal.add_field(label="ID", type="number", value=query.id);
        common_entity_modal.add_field(label="Name", type="text", value=query.name);
        common_entity_modal.add_field(label="Desctription", type="text_area", value=query.description);
        common_entity_modal.add_field(label="SQL", type="text_area", value=query.sql_query);
        common_entity_modal.add_callbacks(submit_callback=(success_callback, error_callback)=> 
                                    delete_query_callback(success_callback, error_callback),
                                    success_callback=()=>table.refresh(kblayersubscription.get_custom_query_info));
        common_entity_modal.show();
        
    },
}
