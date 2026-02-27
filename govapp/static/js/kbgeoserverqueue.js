var kbgeoserverweb = { 
    var: {
        geoserverqueue_list:"/api/publish/geoserverweb/"
    },
    init_dashboard: function() { 
        $( "#geoserver-queue-limit" ).change(function() {
            common_pagination.var.current_page=0;
            kbgeoserverweb.get_geoserverqueue();
        });

        kbgeoserverweb.get_geoserverqueue();
    },
    get_geoserverqueue: function(params_str){
        if (!params_str){
            params = {
                limit: $('#geoserver-queue-limit').val(),
            }

            params_str = utils.make_query_params(params);
        }

        let url = kbgeoserverweb.var.geoserverqueue_list;
        url += "?limit="+$('#geoserver-queue-limit').val();
        url += "&offset="+0; 
        
        $.ajax({
            url: kbgeoserverweb.var.geoserverqueue_list+"?"+params_str,
            method: 'GET',
            dataType: 'json',
            contentType: 'application/json',
            headers: {'X-CSRFToken' : $("#csrfmiddlewaretoken").val()},
            success: (response) => {
                const queue_type_label = {
                    'PUBLISH': 'Publish',
                    'PURGE_CACHE': 'Purge Cache',
                };
                for(let i in response.results){
                    if(response.results[i].status == 'FAILED') response.results[i].success = false;
                    else if(response.results[i].status == 'PUBLISHED') response.results[i].success = true;
                    else response.results[i].success = null;
                    response.results[i].queue_type_label = queue_type_label[response.results[i].queue_type] || response.results[i].queue_type;
                }

                const tbody = $('#geoserver-queue-tbody');
                table.set_tbody(tbody, response.results, [
                    {id:"text"},
                    {queue_type_label:'text'},
                    {name:"text"}, 
                    {submitter:'text'}, 
                    {status:'text'}, 
                    {success:'boolean'}, 
                    {started_at:'text'}, 
                    {publishing_result:'text'}, 
                    {created_at:'text'}
                ]);
                if(response.results == 0){
                    table.message_tbody(tbody, "No results found");
                }
                common_pagination.init(response.count, params, kbgeoserverweb.get_geoserverqueue, $('#paging_navi'));
            },
            error: (error)=> {
                table.message_tbody(tbody, "No results found");
                common_entity_modal.show_alert("An error occured while getting geoserver queue.");
            },
        });
    },
}
