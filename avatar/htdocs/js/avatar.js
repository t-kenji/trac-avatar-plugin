$(function () {
    if (typeof jQuery.ui !== 'undefined') {
        $('.avatar').tooltip({
            items: '.avatar',
            content: function () {
                var src = $(this).attr('src');
                return '<img class="avatar detail" src="' + src + '" />';
            }
        });
    }
});
