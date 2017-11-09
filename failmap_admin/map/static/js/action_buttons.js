// will convert admin action dropdown menu into individual buttons
// https://stackoverflow.com/questions/37318762/django-admin-display-actions-as-buttons
// modified to work on lists with more than 10 items.
(function ($) {

    function fix_actions() {
        var container = $('div.actions');

        container.find('label, button').hide();

        var buttons = $('<div></div>')
            .prependTo(container)
            .css('display', 'inline')
            .addClass('class', 'action-buttons');

        container.find('option:gt(0)').each(function () {
            $('<button>')
                .appendTo(buttons)
                .attr('name', this.value)
                .addClass('button')
                .text(this.text)
                .click(function () {
                    container.find('select')
                        .find(':selected').attr('selected', '').end()
                        .find('[value=' + this.name + ']').attr('selected', 'selected');
                    $('#changelist-form button[name="index"]').click();
                });
        });
    };

    $(function () {
        fix_actions();
    });
})(django.jQuery);
