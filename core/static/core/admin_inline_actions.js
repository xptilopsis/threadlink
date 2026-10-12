/* D13: inline-actions confirm dialog (with a "Do not ask again" option via localStorage) */
(function () {
    "use strict";

    var KEY_PREFIX = "tl_no_confirm:";

    function stored(key) {
        try { return window.localStorage.getItem(KEY_PREFIX + key) === "1"; }
        catch (e) { return false; }
    }

    function remember(key) {
        try { window.localStorage.setItem(KEY_PREFIX + key, "1"); } catch (e) {}
    }

    function getCookie(name) {
        var m = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
        return m ? decodeURIComponent(m[2]) : "";
    }

    function submitAction(actionName, objectId) {
        var form = document.createElement("form");
        form.method = "post";
        form.style.display = "none";
        function add(n, v) {
            var i = document.createElement("input");
            i.type = "hidden";
            i.name = n;
            i.value = v;
            form.appendChild(i);
        }
        add("csrfmiddlewaretoken", getCookie("csrftoken"));
        add("action", actionName);
        add("_selected_action", objectId);
        add("index", "0");
        document.body.appendChild(form);
        form.submit();
    }

    function openConfirm(message, key, onOk) {
        var overlay = document.createElement("div");
        overlay.className = "tl-modal-overlay";

        var modal = document.createElement("div");
        modal.className = "tl-modal";

        var msg = document.createElement("div");
        msg.className = "tl-modal-msg";
        msg.textContent = message;
        modal.appendChild(msg);

        var label = document.createElement("label");
        label.className = "tl-modal-noremind";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        label.appendChild(cb);
        label.appendChild(document.createTextNode("Do not ask again"));
        modal.appendChild(label);

        var actions = document.createElement("div");
        actions.className = "tl-modal-actions";

        var cancel = document.createElement("button");
        cancel.type = "button";
        cancel.textContent = "Cancel";
        cancel.addEventListener("click", function () {
            document.body.removeChild(overlay);
        });

        var ok = document.createElement("button");
        ok.type = "button";
        ok.className = "tl-primary";
        ok.textContent = "OK";
        ok.addEventListener("click", function () {
            if (cb.checked) { remember(key); }
            document.body.removeChild(overlay);
            onOk();
        });

        actions.appendChild(cancel);
        actions.appendChild(ok);
        modal.appendChild(actions);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        ok.focus();
    }

    function openModal(link, key) {
        openConfirm(
            link.getAttribute("data-confirm") || "Confirm this action?",
            key,
            function () {
                var actionName = link.getAttribute("data-action-name");
                if (actionName) {
                    submitAction(actionName, link.getAttribute("data-object-id"));
                } else {
                    window.location.href = link.href;
                }
            }
        );
    }

    document.addEventListener("click", function (e) {
        var el = e.target;
        var link = el && el.closest ? el.closest("a[data-confirm]") : null;
        if (!link) { return; }
        var key = link.getAttribute("data-key") || link.href;
        var actionName = link.getAttribute("data-action-name");
        e.preventDefault();
        if (stored(key)) {
            if (actionName) {
                submitAction(actionName, link.getAttribute("data-object-id"));
            } else {
                window.location.href = link.href;
            }
            return;
        }
        openModal(link, key);
    });

    /* D13: confirm before running verify/destructive bulk actions (Approve/Reject)
       via the changelist action dropdown ("Go"). Reuses the same modal + "Do not ask again". */
    var BATCH_CONFIRM = {
        approve_selected: "Approve the selected run(s)? This writes confirmed results.",
        reject_selected: "Reject the selected run(s)? This cannot be undone."
    };

    function submitChangelist(form) {
        if (!form.querySelector('input[name="index"]')) {
            var i = document.createElement("input");
            i.type = "hidden";
            i.name = "index";
            i.value = "0";
            form.appendChild(i);
        }
        form.submit();
    }

    document.addEventListener("submit", function (e) {
        var form = e.target;
        if (!form || form.id !== "changelist-form") { return; }
        var sel = form.querySelector('select[name="action"]');
        var action = sel ? sel.value : "";
        var message = action ? BATCH_CONFIRM[action] : null;
        if (!message) { return; }
        var key = "batch:" + action;
        e.preventDefault();
        if (stored(key)) {
            submitChangelist(form);
            return;
        }
        openConfirm(message, key, function () { submitChangelist(form); });
    });
})();