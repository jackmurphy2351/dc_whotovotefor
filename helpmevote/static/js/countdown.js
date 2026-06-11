// Live countdown to polls closing. The deadline is rendered into
// data-deadline as an ISO-8601 string with an explicit timezone offset
// (8:00 PM Eastern on June 16, 2026), so the difference against the
// viewer's clock is correct regardless of their local timezone.
(function () {
  "use strict";

  var root = document.getElementById("poll-countdown");
  if (!root) {
    return;
  }

  var deadline = new Date(root.dataset.deadline).getTime();
  if (isNaN(deadline)) {
    return;
  }

  var clock = root.querySelector(".poll-countdown__clock");
  var heading = root.querySelector(".poll-countdown__heading");
  var closed = root.querySelector(".poll-countdown__closed");
  var fields = {
    days: root.querySelector('[data-unit="days"]'),
    hours: root.querySelector('[data-unit="hours"]'),
    minutes: root.querySelector('[data-unit="minutes"]'),
    seconds: root.querySelector('[data-unit="seconds"]'),
  };

  var timer = null;

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function showClosed() {
    if (clock) {
      clock.hidden = true;
    }
    if (heading) {
      heading.hidden = true;
    }
    if (closed) {
      closed.hidden = false;
    }
    if (timer !== null) {
      clearInterval(timer);
    }
  }

  function tick() {
    // Read the current moment on every tick so the countdown stays
    // accurate even if the tab was backgrounded or the clock drifts.
    var remaining = deadline - Date.now();

    if (remaining <= 0) {
      fields.days.textContent = "0";
      fields.hours.textContent = "00";
      fields.minutes.textContent = "00";
      fields.seconds.textContent = "00";
      showClosed();
      return;
    }

    var totalSeconds = Math.floor(remaining / 1000);
    var days = Math.floor(totalSeconds / 86400);
    var hours = Math.floor((totalSeconds % 86400) / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;

    fields.days.textContent = String(days);
    fields.hours.textContent = pad(hours);
    fields.minutes.textContent = pad(minutes);
    fields.seconds.textContent = pad(seconds);
  }

  tick();
  if (deadline - Date.now() > 0) {
    timer = setInterval(tick, 1000);
  }
})();
