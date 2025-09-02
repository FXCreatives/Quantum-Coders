document.addEventListener('DOMContentLoaded', () => {
    const lecturerChoice = document.getElementById('user_choice1');
    const studentChoice = document.getElementById('user_choice2');

    const createAccountLink = document.querySelector('#create_account a');
    const loginLink = document.querySelector('#login a');

    const roleChoices = document.getElementsByName('user');

    // Helper function to update links dynamically
    function updateLinks() {
        if (studentChoice.checked) {
            createAccountLink.href = 'student_create_account.html';
            loginLink.href = 'student_login.html';
        } else if (lecturerChoice.checked) {
            createAccountLink.href = 'lecturer_create_account.html';
            loginLink.href = 'lecturer_login.html';
        }
    }

    // Add event listeners to all role radio buttons
    Array.from(roleChoices).forEach(radio => {
        radio.addEventListener('change', updateLinks);
    });

    // Run once at start to ensure default state
    updateLinks();
});
