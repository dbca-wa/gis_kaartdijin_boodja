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
                    response.results[i].queue_type_label = queue_type_label[response.results[i].queue_type] || response.results[i].queue_type;
                }

                const tbody = $('#geoserver-queue-tbody');
                table.set_tbody(tbody, response.results, [
                    {id:"text"},
                    {queue_type_label:'text'},
                    {name: {type: 'link', url: (row) => `/publish/${row.publish_entry}/`}},
                    {submitter:'text'}, 
                    {status: {type: 'badge', classes: (status) => {
                        const map = {
                            'Queued':               'bg-primary',
                            'Converting':           'bg-warning text-dark',
                            'Published':            'bg-success',
                            'Conversion Failed':    'bg-danger',
                            'Awaiting Transfer':    'bg-info text-dark',
                            'Transferring':         'bg-warning text-dark',
                            'Transfer Failed':      'bg-danger',
                            'Awaiting Publishing': 'bg-info text-dark',
                            'Publishing Failed':   'bg-danger',
                            'PURGED':               'bg-secondary',
                            'FAILED':               'bg-danger',
                        };
                        return map[status] || 'bg-secondary';
                    }}},
                    {started_at:'datetime'}, 
                    {publishing_result:'text'}, 
                    {created_at:'datetime'}
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
