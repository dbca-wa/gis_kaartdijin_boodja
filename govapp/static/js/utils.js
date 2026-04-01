var utils={
    make_query_params: function (params){
        var url_params = "";
    
        if (params){
            for (var key in params){
                if(params[key])
                    url_params += "&" + key + "=" + params[key];
            }
        }
        return url_params;
    },
    validate_email: function (email) {
        if(!email) return false;
        var emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        $('#common-entity-modal-error').hide();
        if (!emailRegex.test(email)) {
            throw new Error("Wrong email format.");
        }
        return email;
    },
    validate_empty_input: function(key, val, msg=key+" is required."){
        if(!val){
            throw new Error(msg);
        }
        return val;
    },
    validate_number: function(key, val, msg="Please enter a valid "+key+". (must be positive number)"){
        if(isNaN(val) || val < 0){
            throw new Error(msg);
        }
        return val;
    },
   convert_date_format: function(date_str, format, hh, mm, ss){
        if(!date_str) return null;
        // make a moment object by original format
        let original_format = format.toUpperCase()+'-hh:mm:ss';
        date_str = date_str + '-' + hh + ":" + mm + ":" + ss;
        let target_format = 'YYYY-MM-DDTHH:mm:ss';
        let converted_str = this.convert_datetime_format(date_str, target_format, original_format);
        return converted_str
    },
    convert_datetime_format: function(datetime_str, target_format, original_format){
        if(!datetime_str) return null;
        let original_datetime;
        if(original_format){
            // make a moment object by original format
            original_datetime = moment(datetime_str, original_format);
        }else{
            original_datetime = moment(datetime_str);
        }
        
        return original_datetime.format(target_format);
    },
    call_get_api: function(url, success_callback, error_callback){
        $.ajax({
            url: url,
            type: 'GET',
            contentType: 'application/json',
            success: (response) => {
                if(!response || !response.results){
                    error_callback();
                    return;
                }
                success_callback();
            },
            error: error_callback,
        });
    },
    enter_keyup: function(text_input, callback){
        text_input.on("keyup", function(e) {
            if (e.keyCode === 13) { // eneter key
                callback();
            }
          });
    },
    restricted_icon: function(){
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="restricted-icon"><path d="M367.2 412.5L99.5 144.8C77.1 176.1 64 214.5 64 256c0 106 86 192 192 192c41.5 0 79.9-13.1 111.2-35.5zm45.3-45.3C434.9 335.9 448 297.5 448 256c0-106-86-192-192-192c-41.5 0-79.9 13.1-111.2 35.5L412.5 367.2zM0 256a256 256 0 1 1 512 0A256 256 0 1 1 0 256z"/></svg>'
    },
    public_icon: function(){
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="public-icon"><path d="M352 256c0 22.2-1.2 43.6-3.3 64l-185.3 0c-2.2-20.4-3.3-41.8-3.3-64s1.2-43.6 3.3-64l185.3 0c2.2 20.4 3.3 41.8 3.3 64zm28.8-64l123.1 0c5.3 20.5 8.1 41.9 8.1 64s-2.8 43.5-8.1 64l-123.1 0c2.1-20.6 3.2-42 3.2-64s-1.1-43.4-3.2-64zm112.6-32l-116.7 0c-10-63.9-29.8-117.4-55.3-151.6c78.3 20.7 142 77.5 171.9 151.6zm-149.1 0l-176.6 0c6.1-36.4 15.5-68.6 27-94.7c10.5-23.6 22.2-40.7 33.5-51.5C239.4 3.2 248.7 0 256 0s16.6 3.2 27.8 13.8c11.3 10.8 23 27.9 33.5 51.5c11.6 26 20.9 58.2 27 94.7zm-209 0L18.6 160C48.6 85.9 112.2 29.1 190.6 8.4C165.1 42.6 145.3 96.1 135.3 160zM8.1 192l123.1 0c-2.1 20.6-3.2 42-3.2 64s1.1 43.4 3.2 64L8.1 320C2.8 299.5 0 278.1 0 256s2.8-43.5 8.1-64zM194.7 446.6c-11.6-26-20.9-58.2-27-94.6l176.6 0c-6.1 36.4-15.5 68.6-27 94.6c-10.5 23.6-22.2 40.7-33.5 51.5C272.6 508.8 263.3 512 256 512s-16.6-3.2-27.8-13.8c-11.3-10.8-23-27.9-33.5-51.5zM135.3 352c10 63.9 29.8 117.4 55.3 151.6C112.2 482.9 48.6 426.1 18.6 352l116.7 0zm358.1 0c-30 74.1-93.6 130.9-171.9 151.6c25.5-34.2 45.2-87.7 55.3-151.6l116.7 0z"/></svg>'
    },
    format_file_size: function(bytes) {
        if (bytes == null) return '---';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
    }
}
