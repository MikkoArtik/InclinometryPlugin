$(document).ready(function() {

    let linkItem = $(".fly-sheet__link--click");

    linkItem.on("click", function(event) {

        event.preventDefault();
        $(this).next().toggle().toggleClass('fly-sheet__sub-menu--open');

    });



});