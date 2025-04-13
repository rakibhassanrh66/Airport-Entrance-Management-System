// Handle search form submission
document.getElementById('searchForm').addEventListener('submit', function(event) {
    event.preventDefault();  // Prevent the default form submission

    const flightNumber = document.getElementById('flightNumber').value;
    const searchResultDiv = document.getElementById('searchResult');

    if (flightNumber) {
        // AJAX request to search for flight
        const xhr = new XMLHttpRequest();
        xhr.open("GET", "searchFlight.php?flightNumber=" + flightNumber, true);
        xhr.onreadystatechange = function () {
            if (xhr.readyState == 4 && xhr.status == 200) {
                searchResultDiv.innerHTML = xhr.responseText;
            }
        };
        xhr.send();
    } else {
        searchResultDiv.innerHTML = "Please enter a flight number.";
    }
});
