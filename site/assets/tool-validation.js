/**
 * Inline form validation banner for /tools/* calculators.
 * Loaded synchronously before page inline scripts.
 */
(function (global) {
  function $(id) {
    return document.getElementById(id);
  }

// Localised pages carry window.DUCT_I18N (scripts/build_site_i18n.py); the literal must stay inline at the call.
var ductT = window.ductT || function (s) { var m = window.DUCT_I18N; return (m && m[s]) || s; };

  global.DuctToolFormError = {
    clear: function (errorElId, inputIds) {
      var err = $(errorElId);
      if (err) {
        err.textContent = '';
        err.classList.remove('show');
      }
      (inputIds || []).forEach(function (id) {
        var inp = $(id);
        if (!inp) return;
        inp.classList.remove('field-invalid');
        inp.removeAttribute('aria-invalid');
      });
    },

    show: function (errorElId, message, invalidInputIds) {
      var err = $(errorElId);
      if (!err) return;
      err.textContent = message;
      err.classList.add('show');
      (invalidInputIds || []).forEach(function (id) {
        var inp = $(id);
        if (!inp) return;
        inp.classList.add('field-invalid');
        inp.setAttribute('aria-invalid', 'true');
      });
      err.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },

    bindClear: function (errorElId, inputIds) {
      var self = this;
      (inputIds || []).forEach(function (id) {
        var inp = $(id);
        if (!inp) return;
        inp.addEventListener('input', function () {
          self.clear(errorElId, inputIds);
        });
      });
    }
  };

  // A calculator is a blank form until someone types, and a blank form on a
  // landing page is a page with nothing on it. Seed the fields from their
  // own "e.g." placeholders and run the calculation once, so the page opens
  // on a worked example: coloured cards, a verdict, the shape of the answer.
  // The note under the heading says so; the first keystroke takes the note
  // and the example results away and the tool is back to its normal flow.
  global.DuctToolExample = {
    seed: function (inputIds, buttonId, resultsId) {
      var button = $(buttonId), results = $(resultsId);
      if (!button || !results) return;
      var seeded = [];
      (inputIds || []).forEach(function (id) {
        var inp = $(id);
        if (!inp || inp.value !== '') return;
        var m = /e\.g\.\s*(-?[\d.]+)/.exec(inp.getAttribute('placeholder') || '');
        if (!m) return;
        inp.value = m[1];
        seeded.push(inp);
      });
      if (!seeded.length) return;
      button.click();
      if (!results.classList.contains('visible')) return;
      var note = document.createElement('p');
      note.className = 'tool-example-note';
      note.textContent = ductT('Example numbers. Change any field and calculate again for yours.');
      results.insertBefore(note, results.firstChild);
      var undo = function () {
        if (note.parentNode) note.parentNode.removeChild(note);
        results.classList.remove('visible');
        seeded.forEach(function (inp) { inp.removeEventListener('input', undo); });
      };
      seeded.forEach(function (inp) { inp.addEventListener('input', undo); });
    }
  };
})(typeof window !== 'undefined' ? window : this);
