/**
 * Inline form validation banner for /tools/* calculators.
 * Loaded synchronously before page inline scripts.
 */
(function (global) {
  function $(id) {
    return document.getElementById(id);
  }

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
})(typeof window !== 'undefined' ? window : this);
