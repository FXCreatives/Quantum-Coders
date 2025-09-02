const lecturerChoice = document.getElementById('user_choice1');
const studentChoice = document.getElementById('user_choice2');

const createAccountLink = document.querySelector('#create_account a');
const loginLink = document.querySelector('#login a');

const roleChoices = document.getElementsByName('user');

roleChoices.forEach(radio => {
    radio.addEventListener('change', () => {
        if (studentChoice && studentChoice.checked) {
            createAccountLink.href = 'student_create_account.html';
            loginLink.href = 'student_login.html';
        } else if (lecturerChoice && lecturerChoice.checked) {
            createAccountLink.href = 'lecturer_create_account.html';
            loginLink.href = 'lecturer_login.html';
        }
    });
});

if (lecturerChoice && lecturerChoice.checked) {
    createAccountLink.href = 'lecturer_create_account.html';
    loginLink.href = 'lecturer_login.html';
}
