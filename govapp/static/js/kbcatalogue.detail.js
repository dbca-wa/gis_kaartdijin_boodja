var kbcatalogue_detail = {
    var: {
        catalogue_email_notification:"/api/catalogue/notifications/emails/",
        catalogue_email_notification_type_url:"/api/catalogue/notifications/emails/type",
        log_communication_type_url:"/api/logs/communications/type/",
        catalogue_table_date_format: "DD MMM YYYY HH:mm:ss",
        catalogue_email_notification_type:null,    // will be filled during initiation
        communication_type:null,    // will be filled during initiation
    },

    init_catalogue_detail: function(){
        $("#catalogue-entry-btn-save" ).click(() => kbcatalogue_detail.save_catalogue('save'));
        $("#catalogue-entry-btn-save-exit" ).click(() => kbcatalogue_detail.save_catalogue('save-and-exit'));      
        $("#catalogue-detail-btn-add-notification" ).click(kbcatalogue_detail.show_add_email_notification_modal);
        $("#catalogue-detail-notification-order-by" ).change(()=>table.refresh(kbcatalogue_detail.get_email_notification));
        $("#catalogue-detail-notification-limit" ).change(()=>table.refresh(kbcatalogue_detail.get_email_notification));
        // $("#log_actions_show" ).click(kbcatalogue_detail.show_action_log);
        $("#log_actions_show" ).click(handle_action_log.show_action_log);
        $("#log_communication_show" ).click(kbcatalogue_detail.show_communication_log);
        $("#log_communication_add" ).click(kbcatalogue_detail.add_communication_log);

        kbcatalogue_detail.var.has_edit_access = $('#has_edit_access').val() == 'True';
        kbcatalogue_detail.retrieve_communication_types();
        kbcatalogue_detail.retrieve_noti_types(()=>table.refresh(kbcatalogue_detail.get_email_notification));
    },
    retrieve_noti_types: function(post_callback){
        $.ajax({
            url: kbcatalogue_detail.var.catalogue_email_notification_type_url,
            type: 'GET',
            contentType: 'application/json',
            success: (response) => {
                var noti_type = {}
                for(let i in response.results){
                    const type = response.results[i];
                    noti_type[type.id] = type.label;
                }
                kbcatalogue_detail.var.catalogue_email_notification_type = noti_type;
                post_callback();
            },
            error: (error)=> {
                common_entity_modal.show_alert("An error occured while getting email notification type.");
                // console.error(error);
            },
        });
    },
    retrieve_communication_types: function(){
        $.ajax({
            url: kbcatalogue_detail.var.log_communication_type_url,
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
                kbcatalogue_detail.var.communication_type = communication_type;
            },
            error: (error)=> {
                common_entity_modal.show_alert("An error occured while getting retrieve communication types.");
                // console.error(error);
            },
        });
    },
    save_catalogue: function(save_status) {        
        var catalogue_id = $('#catalogue_entry_id').val();
        var cataloguename = $('#catalogue-entry-name').val();
        var cataloguecustodianentry = $('#catalogue-custodian-entry').val();
        var permission_type = $('#catalogue-permission-type').val();
        var default_crs = $('#catalogue-default-crs').val();
        
        var cataloguedescription = $('#catalogue-entry-description').val();
        var post_data = {
            "name": cataloguename,
            "description": cataloguedescription,
            "custodian": cataloguecustodianentry,
            "permission_type": permission_type,
            "default_crs": default_crs || null
        };
        var csrf_token = $("#csrfmiddlewaretoken").val();
        var pagetab = $('#pagetab').val();

        $.ajax({
            url: kbcatalogue.var.catalogue_data_url+catalogue_id+"/",
            type: 'PUT',
            headers: {'X-CSRFToken' : csrf_token},
            data: JSON.stringify(post_data),
            contentType: 'application/json',
            success: function (response) {
                if (save_status == 'save-and-exit') {
                    window.location = '/catalogue/entries/';
                } else {
                    window.location = "/catalogue/entries/"+catalogue_id+"/"+pagetab+"/"; 
                }
            },
            error: function (error) {
                common_entity_modal.show_alert("ERROR Saving.");
            },
        });
    },

    //-- for Email Notification --//
    get_email_notification: function(params_str){
        if (!params_str){
            params = {
                catalogue_entry:$('#catalogue_entry_id').val(),
                limit:          $('#catalogue-detail-notification-limit').val(),
                order_by:       $('#catalogue-detail-notification-order-by').val()
            }

            params_str = utils.make_query_params(params);
        }

        $.ajax({
            url: kbcatalogue_detail.var.catalogue_email_notification+'?'+params_str,
            method: 'GET',
            contentType: 'application/json',
            success: function (response) {
                if(!response){
                    $('#catalogue-detail-notification-tbody').html("<tr><td colspan='7' class='text-center'>No results found</td></tr>");
                    return;
                }

                let buttons = {};
                if(kbcatalogue_detail.var.has_edit_access){
                    buttons={Update:(noti)=>kbcatalogue_detail.show_update_email_notification_modal(noti),
                        Delete:(noti)=>kbcatalogue_detail.show_delete_email_notification_modal(noti)};
                }
                    
                // change type number to name
                for(let i in response.results){
                    response.results[i].type_str = kbcatalogue_detail.var.catalogue_email_notification_type[response.results[i].type];
                }

                table.set_tbody($('#catalogue-detail-notification-tbody'), response.results, 
                                // columns=[{id:'text'}, {name:'text'}, {type_str:'text'}, {email:'text'}, {active:'switch'}], 
                                columns=[{id:'text'}, {name:'text'}, {type_str:'text'}, {email:'text'}, {active:'boolean'}], 
                                buttons=buttons);
                common_pagination.init(response.count, params, kbcatalogue_detail.get_email_notification, $('#notification-paging-navi'));
            },
            error: function (error) {
                common_entity_modal.show_alert("Error occured.");
                // console.log('Error occured.'+ error);
            },
        });
    },

    //-- for Email Notification modal --//
    show_add_email_notification_modal: function(){
        console.log('in show_add_email_notification_modal')
        common_entity_modal.init("Add New Email Notification", "submit");
        let name_id = common_entity_modal.add_field(label="Name", type="text");
        let type_id = common_entity_modal.add_field(label="Type", type="select", value=null, option_map=kbcatalogue_detail.var.catalogue_email_notification_type);
        let email_id = common_entity_modal.add_field(label="Email", type="email");
        let active_id = common_entity_modal.add_field(label="Active", type="switch");
        common_entity_modal.add_callbacks(submit_callback=(success_callback, error_callback)=> 
                                            kbcatalogue_detail.write_email_notification(success_callback, error_callback, name_id, type_id, email_id, active_id),
                                            success_callback=()=>table.refresh(kbcatalogue_detail.get_email_notification));
        common_entity_modal.show();
    },

    show_update_email_notification_modal: function(prev){
        console.log('in show_update_email_notification_modal')
        common_entity_modal.init("Update Email Notification", "submit");
        let name_id = common_entity_modal.add_field(label="Name", type="text", value=prev.name);
        let type_id = common_entity_modal.add_field(label="Type", type="select", value=prev.type, option_map=kbcatalogue_detail.var.catalogue_email_notification_type);
        let email_id = common_entity_modal.add_field(label="Email", type="email", value=prev.email);
        let active_id = common_entity_modal.add_field(label="Active", type="switch", value=prev.active);
        common_entity_modal.add_callbacks(submit_callback=(success_callback, error_callback)=> 
                                            kbcatalogue_detail.write_email_notification(success_callback, error_callback, name_id, type_id, email_id, active_id, prev.id),
                                            success_callback=()=>table.refresh(kbcatalogue_detail.get_email_notification));
        common_entity_modal.show();
    },
    write_email_notification: function(success_callback, error_callback, name_id, type_id, email_id, active_id, noti_id){
        // get & validation check
        const name = utils.validate_empty_input('name', $('#'+name_id).val());
        const type = utils.validate_empty_input('type', $('#'+type_id).val());
        const email = utils.validate_empty_input('email', $('#'+email_id).val());
        utils.validate_email(email);
        const active = $('#'+active_id).prop('checked');
        
        // make data body
        var email_noti_data = {
            name:name,
            type:type,
            email:email,
            active:active,
            catalogue_entry:$('#catalogue_entry_id').val()
        };
        var url = kbcatalogue_detail.var.catalogue_email_notification;
        var method = 'POST';
        if(noti_id){
            delete email_noti_data['catalogue_entry'];
            url += noti_id+'/';
            method = 'PUT';
        }

        // call POST API
        $.ajax({
            url: url,
            method: method,
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            data: JSON.stringify(email_noti_data),
            success: success_callback,
            error: error_callback
        });
    },

    show_delete_email_notification_modal: function(target){
        console.log('in show_delete_email_notification_modal')
        common_entity_modal.init("Delte Email Notification", "delete");
        common_entity_modal.add_field(label="Name", type="text", value=target.name);
        common_entity_modal.add_field(label="Type", type="select", value=target.type, option_map=kbcatalogue_detail.var.catalogue_email_notification_type);
        common_entity_modal.add_field(label="Email", type="email", value=target.email);
        common_entity_modal.add_field(label="Active", type="switch", value=target.active);
        common_entity_modal.add_callbacks(submit_callback=(success_callback, error_callback)=> 
                                            kbcatalogue_detail.delete_email_notification(success_callback, error_callback, target.id),
                                            success_callback=()=>table.refresh(kbcatalogue_detail.get_email_notification));
        common_entity_modal.show();
    },

    delete_email_notification: function(success_callback, error_callback, noti_id){
        $.ajax({
            url: kbcatalogue_detail.var.catalogue_email_notification+noti_id+"/",
            method: 'DELETE',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            success: success_callback, 
            error: error_callback
        });
    },
    // show_action_log: function(){
    //     console.log('in kbcatalogue.detail.js')

    //     common_entity_modal.init("Action log", "info");
    //     common_entity_modal.init_talbe();
    //     let thead = common_entity_modal.get_thead();
    //     table.set_thead(thead, {Who:3, What:5, When:4});
    //     common_entity_modal.get_limit().change(()=>kbcatalogue_detail.get_action_log());
    //     common_entity_modal.get_search().keyup((event)=>{
    //         if (event.which === 13 || event.keyCode === 13){
    //             event.preventDefault();
    //             kbcatalogue_detail.get_action_log()
    //         }
    //     });
    //     common_entity_modal.show();

    //     kbcatalogue_detail.get_action_log();
    // },
    // get_action_log: function(params_str){
    //     if(!params_str){
    //         params = {
    //             limit:  common_entity_modal.get_limit().val(),
    //             search: common_entity_modal.get_search().val(),
    //         }

    //         params_str = utils.make_query_params(params);
    //     }
    
    //     var catalogue_entry_id = $('#catalogue_entry_id').val();
    //     $.ajax({
    //         url: kbcatalogue.var.catalogue_data_url+catalogue_entry_id+"/logs/actions/?"+params_str,
    //         method: 'GET',
    //         dataType: 'json',
    //         contentType: 'application/json',
    //         success: function (response) {
    //             if(!response || !response.results){
    //                 table.message_tbody(common_entity_modal.get_tbody(), "No results found");
    //                 return;
    //             }
    //             for(let i in response.results){
    //                 response.results[i]['when'] = utils.convert_datetime_format(response.results[i].when, kbcatalogue_detail.var.catalogue_table_date_format); 
    //             }
    //             table.set_tbody(common_entity_modal.get_tbody(), response.results, [{username:"text"}, {what:'text'}, {when:'text'}]);
    //             common_pagination.init(response.count, params, kbcatalogue_detail.get_action_log, common_entity_modal.get_page_navi());
    //         },
    //         error: function (error){
    //             common_entity_modal.show_error_modal(error);
    //         }
    //     });
    // },
    show_communication_log: function(){
        common_entity_modal.init("Communication log", "info");
        common_entity_modal.init_talbe();
        let thead = common_entity_modal.get_thead();
        table.set_thead(thead, {User:2, To:2, Cc:2, From:2, Subject:2, Text:2});
        common_entity_modal.get_limit().change(()=>kbcatalogue_detail.get_communication_log());
        common_entity_modal.get_search().keyup((event)=>{
            if (event.which === 13 || event.keyCode === 13){
                event.preventDefault();
                kbcatalogue_detail.get_communication_log()
            }
        });
        common_entity_modal.show();

        kbcatalogue_detail.get_communication_log();
    },
    get_communication_log: function(params_str){
        if(!params_str){
            params = {
                limit:  common_entity_modal.get_limit().val(),
                search: common_entity_modal.get_search().val(),
            }

            params_str = utils.make_query_params(params);
        }
    
        var catalogue_entry_id = $('#catalogue_entry_id').val();
        $.ajax({
            url: kbcatalogue.var.catalogue_data_url+catalogue_entry_id+"/logs/communications/?"+params_str,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            success: function (response) {
                if(!response || !response.results){
                    table.message_tbody(common_entity_modal.get_tbody(), "No results found");
                    return;
                }
                for(let i in response.results){
                    response.results[i]['created_at'] = utils.convert_datetime_format(response.results[i].created_at, kbcatalogue_detail.var.catalogue_table_date_format); 
                }
                table.set_tbody(common_entity_modal.get_tbody(), response.results, 
                                [{username:"text"}, {to:'text'}, {cc:'text'}, {from:'text'}, {subject:'text'}, {text:'text'}]);
                common_pagination.init(response.count, params, kbcatalogue_detail.get_communication_log, common_entity_modal.get_page_navi());
            },
            error: function (error){
                common_entity_modal.show_error_modal(error);
            }
        });
    },
    add_communication_log: function(){
        common_entity_modal.init("Add New Communication log", "submit");
        let type_id = common_entity_modal.add_field(label="Communication Type", type="select", value=null, option_map=kbcatalogue_detail.var.communication_type);
        let to_id = common_entity_modal.add_field(label="To", type="text");
        let cc_id = common_entity_modal.add_field(label="Cc", type="text");
        let from_id = common_entity_modal.add_field(label="From", type="text");
        let subject_id = common_entity_modal.add_field(label="Subject", type="text");
        let text_id = common_entity_modal.add_field(label="Text", type="text_area");

        common_entity_modal.add_callbacks(submit_callback=(success_callback, error_callback)=> 
                            kbcatalogue_detail.create_communication_log(success_callback, error_callback, type_id, to_id, cc_id, from_id, subject_id, text_id));
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
        var url = kbcatalogue.var.catalogue_data_url+$('#catalogue_entry_id').val()+"/logs/communications/";
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
}