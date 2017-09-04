/*app-specific javascript goes here */

function searchFocus(e) {
// Update search input content on focus
if (e.value == 'search') {
  e.value = '';
  e.className = '';
  searchIsDisabled = false;
  }
}

function searchBlur(e) {
 // Update search input content on blur
if (e.value == '') {
  e.value = 'search';
  e.className = 'disabled';
  searchIsDisabled = true;
  }
}
