(function () {
  "use strict";

  var DELAY_THRESHOLD_MS = 15 * 60 * 1000; // 15 minutes

  function getCookie(name) {
    var match = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return match ? match.pop() : "";
  }

  var csrftoken = getCookie("csrftoken");

  function branchQuery() {
    return window.KITCHEN_BRANCH_ID ? "?branch=" + window.KITCHEN_BRANCH_ID : "";
  }

  function showToast(message) {
    var toast = document.getElementById("kitchen-toast");
    if (!toast) return;
    toast.textContent = message;
    toast.style.display = "block";
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {
      toast.style.display = "none";
    }, 4000);
  }

  function postAction(url) {
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrftoken },
    }).then(function (resp) {
      if (!resp.ok) {
        resp.json().then(function (data) {
          showToast(typeof data === "string" ? data : JSON.stringify(data));
        });
      }
    });
  }

  function actionsFor(ticket) {
    var wrap = document.createElement("div");
    var btn = document.createElement("button");
    btn.className = "btn primary";
    if (ticket.kitchen_status === "pending") {
      btn.textContent = "Start Cooking";
      btn.onclick = function () {
        postAction("/api/pos/kitchen/queue/" + ticket.id + "/start-cooking/");
      };
    } else if (ticket.kitchen_status === "cooking") {
      btn.textContent = "Mark Ready";
      btn.onclick = function () {
        postAction("/api/pos/kitchen/queue/" + ticket.id + "/ready/");
      };
    } else if (ticket.kitchen_status === "ready") {
      btn.textContent = "Mark Served";
      btn.onclick = function () {
        postAction("/api/pos/kitchen/queue/" + ticket.id + "/served/");
      };
    }
    wrap.appendChild(btn);
    return wrap;
  }

  function isDelayed(ticket) {
    // started_cooking_at is the only timestamp this ticket shape exposes
    // for an in-progress item; pending tickets have no creation timestamp
    // available here, so delay detection is limited to "cooking" for now.
    if (ticket.kitchen_status !== "cooking" || !ticket.started_cooking_at) return false;
    return Date.now() - new Date(ticket.started_cooking_at).getTime() > DELAY_THRESHOLD_MS;
  }

  function updateEmptyStates() {
    ["pending", "cooking", "ready"].forEach(function (status) {
      var column = document.getElementById("col-" + status);
      if (!column) return;
      var hasTickets = column.querySelector(".ticket") !== null;
      var placeholder = column.querySelector(".empty");
      if (!hasTickets && !placeholder) {
        var p = document.createElement("p");
        p.className = "empty";
        p.textContent = "No tickets.";
        column.appendChild(p);
      } else if (hasTickets && placeholder) {
        placeholder.remove();
      }
    });
  }

  function renderTicket(ticket) {
    if (ticket.kitchen_status === "served" || ticket.kitchen_status === "cancelled") {
      var existing = document.getElementById("ticket-" + ticket.id);
      if (existing) existing.remove();
      updateEmptyStates();
      return;
    }

    var template = document.getElementById("ticket-template");
    var el = document.getElementById("ticket-" + ticket.id);
    if (!el) {
      el = template.content.firstElementChild.cloneNode(true);
      el.id = "ticket-" + ticket.id;
    }

    el.className = "ticket " + ticket.kitchen_status + (isDelayed(ticket) ? " delayed" : "");
    el.querySelector(".t-table").textContent = ticket.table || "Takeaway";
    el.querySelector(".t-item").textContent = ticket.menu_item_name;
    el.querySelector(".t-qty").textContent = ticket.quantity;
    el.querySelector(".notes").textContent = ticket.notes || "";

    var actionsEl = el.querySelector(".t-actions");
    actionsEl.innerHTML = "";
    actionsEl.appendChild(actionsFor(ticket));

    var column = document.getElementById("col-" + ticket.kitchen_status);
    if (column) column.appendChild(el);
    updateEmptyStates();
  }

  function loadInitialQueue() {
    fetch("/api/pos/kitchen/queue/" + branchQuery(), { credentials: "same-origin" })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (tickets) {
        tickets.forEach(renderTicket);
        updateEmptyStates();
      });
  }

  function connectSocket() {
    var scheme = window.location.protocol === "https:" ? "wss://" : "ws://";
    var socket = new WebSocket(scheme + window.location.host + "/ws/kitchen/" + branchQuery());
    socket.onmessage = function (event) {
      renderTicket(JSON.parse(event.data));
    };
    socket.onclose = function () {
      setTimeout(connectSocket, 3000);
    };
  }

  loadInitialQueue();
  connectSocket();
})();
