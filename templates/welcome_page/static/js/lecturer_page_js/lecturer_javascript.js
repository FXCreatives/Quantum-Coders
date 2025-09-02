document.addEventListener("DOMContentLoaded", async function () {
    const TOKEN = sessionStorage.getItem("tapin_token"); // Lecturer auth token
    const classList = document.getElementById("classList");

    // -----------------------------
    // API Helper Function
    // -----------------------------
    async function api(path, options = {}) {
        try {
            const res = await fetch(`http://localhost:8000${path}`, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...(options.headers || {}),
                    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
                },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.error("API Error:", err);
            return { error: "Failed to connect to the server." };
        }
    }

    // -----------------------------
    // Load Classes
    // -----------------------------
    async function loadClasses() {
        classList.innerHTML = `<p style="text-align:center;">Loading...</p>`;
        const res = await api("/api/lecturer/classes");

        classList.innerHTML = "";
        if (res.error || !res.length) {
            classList.innerHTML = `<p style="text-align:center;color:#888;">No classes available.</p>`;
            return;
        }

        res.forEach((cls) => {
            const div = document.createElement("div");
            div.classList.add("class-item");
            div.innerHTML = `
                <div class="class-info" onclick="window.location.href='class_page.html?classId=${cls.id}'">
                    <h3>${cls.class_name}</h3>
                    <p>${cls.course_name} (${cls.course_code})</p>
                    <small>PIN: ${cls.join_pin}</small>
                </div>
            `;
            classList.appendChild(div);
        });
    }

    // Initial load
    await loadClasses();

    // -----------------------------
    // Create Class Modal Logic
    // -----------------------------
    const form = document.getElementById("classForm");
    const modal = document.getElementById("classFormContainer");
    const closeBtn = document.getElementById("closeForm");
    const createBtn = document.getElementById("createClassBtn");
    const generatePinBtn = document.getElementById("generatePin");

    if (createBtn) {
        createBtn.addEventListener("click", () => modal.style.display = "flex");
    }

    if (closeBtn) {
        closeBtn.addEventListener("click", () => modal.style.display = "none");
    }

    if (generatePinBtn) {
        generatePinBtn.addEventListener("click", () => {
            form.joinPin.value = Math.floor(100000 + Math.random() * 900000);
        });
    }

    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const classData = {
                class_name: form.className.value,
                programme: form.programme.value,
                faculty: form.faculty.value,
                department: form.department.value,
                course_name: form.courseName.value,
                course_code: form.courseCode.value,
                level: form.level.value,
                section: form.section.value,
                join_pin: form.joinPin.value
            };

            const res = await api("/api/lecturer/classes", {
                method: "POST",
                body: JSON.stringify(classData)
            });

            if (res.error) {
                alert(res.error);
            } else {
                alert("Class created successfully!");
                form.reset();
                modal.style.display = "none";
                await loadClasses();
            }
        });
    }

    // -----------------------------
    // Sidebar + Theme Toggle
    // -----------------------------
    const toggleBtn = document.getElementById("toggleBtn");
    const sidebar = document.getElementById("sidebar");

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", () => {
            sidebar.classList.toggle("collapsed");
            const icon = toggleBtn.querySelector("i");
            sidebar.classList.contains("collapsed")
                ? icon.classList.replace("fa-bars", "fa-chevron-right")
                : icon.classList.replace("fa-chevron-right", "fa-bars");
            localStorage.setItem("sidebarCollapsed", sidebar.classList.contains("collapsed"));
        });

        if (window.innerWidth <= 768 || localStorage.getItem("sidebarCollapsed") === "true") {
            sidebar.classList.add("collapsed");
        }

        window.addEventListener("resize", () => {
            if (window.innerWidth <= 768) sidebar.classList.add("collapsed");
        });
    }
});
