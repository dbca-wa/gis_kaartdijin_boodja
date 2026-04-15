/*** 
 * This is a util to manage a bootstrap table
 * Core public methods
 *  - set_thead
 *  - set_tbody
 *  - message_body
 *  - refresh
***/
var table={
    
    
    /*** 
    * setting a table head
    * Param
    *  - thead : Jquery object of <thead>
    *  - columns : An object to set columns of head
    *               key - Name of column
    *               value - number of bootstrap grid of column for width
    *  - e.g. {Name:2, Email:4}
    ***/
    set_thead: function (thead, columns){
        thead.empty();

        let tr = $('<tr>');
        for(key in columns){
            let th = $('<th>');
            th.attr('class', 'col-'+columns[key]);
            th.text(key);
            tr.append(th);
        }
        thead.append(tr);
    },

    /*** 
    * setting a table body
    * Param
    *  - thead : Jquery object of <thead>
    *  - columns : An object to set columns of head
    *               key - Name of column
    *               value - number of bootstrap grid of column for width
    *  - e.g. {Name:2, Email:4}
    ***/
    set_tbody: function (tbody, list, columns, buttons=null){
        tbody.empty();

        for(let i in list){
            let row = this._make_row(list[i], columns);
            if(buttons){
                row.append(this._make_button_cell(buttons, tbody.attr("id")+'-row-'+i, list[i]));
            }
            tbody.append(row);
        }
    },
    message_tbody: function(tbody, message){
        tbody.html("<tr><td colspan='7' class='text-center'>" + message + "</td></tr>");
    },

    // ('#catalogue-detail-notification-tbody', response.results, {active:'switch'},
    //                                     buttons={Update:kbcatalogue_detail.show_update_email_notification_modal, 
    //                                             Delete:kbcatalogue_detail.show_delete_email_notification_modal});

    _make_row: function (obj, columns){
        let row = $('<tr>');
        for(let i in columns){
            let key = Object.keys(columns[i])[0];
            if(key in obj){
                if(columns[i][key] == 'switch')
                    row.append(this._make_switch_cell(obj[key]));
                else if(columns[i][key] == 'text')
                    row.append(this._make_text_cell(obj[key]));
                else if(columns[i][key] == 'boolean')
                    row.append(this._make_boolean_cell(obj[key]));
                else if(typeof columns[i][key] === 'object' && columns[i][key].type == 'link')
                    row.append(this._make_link_cell(obj[key], columns[i][key].url(obj)));
            }
        }
        return row;
    },
    _make_text_cell: function(text){
        return $('<td>').text(text);
    },
    _make_link_cell: function(text, url){
        let a = $('<a>').attr('href', url).attr('style', 'text-decoration: none;').text(text);
        return $('<td>').append(a);
    },
    _make_switch_cell: function(checked, disabled=true){
        let div = $('<div>').attr("class", "form-check form-switch");
        let input = $('<input>').attr("class", "form-check-input").attr("type", "checkbox").attr("role", "switch")
                    .prop("checked", checked).prop("disabled", disabled);
        div.append(input);
        return $('<td>').append(div);
    },
    _make_boolean_cell: function(flag){
        let i = $('<i>');
        if(flag == true){
            i.attr("class", "bi bi-check-circle-fill");
            i.attr("style", "color: #08c508;");
        }else if(flag == false){
            i.attr("class", "bi bi-x-circle-fill");
            i.attr("style", "color: #dd0508;");
        }else{
            i.attr("class", "bi bi-dash-circle-fill");
            i.attr("style", "color: #fdbd1a;");
        }
        return $('<td>').append(i);
    },
    _make_button_cell: function(buttons, id_prefix, data){
        // e.g. : buttons={Update:callback(data)}
        let td = $('<td>');
        td.attr("class", "text-end");
        for(let key in buttons){
            if(typeof buttons[key] == 'function'){
                let button = $('<button>').attr("class", "btn btn-primary btn-sm").attr("id", id_prefix+"-"+key.toLowerCase()).text(key);
                button.click(()=>buttons[key](data));
                td.append(button);
                td.append(" ");
            } else {
                if(buttons[key].is_valid(data)){
                    let button = $('<button>').attr("class", "btn btn-primary btn-sm").attr("id", id_prefix+"-"+key.toLowerCase()).text(key);
                    button.click(()=>buttons[key].callback(data));
                    td.append(button);
                    td.append(" ");
                }
            }
        }
        return td;
    },
    refresh: function(draw_table_callback){
        common_pagination.var.current_page = 0;
        draw_table_callback();
    }
}