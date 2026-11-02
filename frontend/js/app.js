const $ = (selector) => document.querySelector(selector);

function guideClosure(message) {
  const dialogue = $("#closure-dialogue");
  if (dialogue) dialogue.textContent = message;
  const accountDialogue = $("#account-closure-dialogue");
  if (accountDialogue) accountDialogue.textContent = message;

  const logMessage = window.pywebview?.api?.log_frontend_message;
  if (typeof logMessage === "function") {
    try {
      Promise.resolve(logMessage(message)).catch((error) => {
        console.error("Closure message could not be written to the terminal log.", error);
      });
    } catch (error) {
      console.error("Closure message could not be written to the terminal log.", error);
    }
  } else {
    console.info("[Closure]", message);
  }
}

function setPill(element, ready) {
  element.textContent = ready ? "Terdaftar" : "Belum terdaftar";
  element.classList.toggle("is-ready", ready);
}

async function initializeAccessPage() {
  const cameraButton = $("#camera-button");
  const captureButton = $("#capture-button");
  const finishFaceButton = $("#finish-face-button");
  const registerUsbButton = $("#register-usb-button");
  const refreshUsbButton = $("#refresh-usb-button");
  const unlockButton = $("#unlock-button");
  const preview = $("#camera-preview");
  const placeholder = $("#camera-placeholder");
  const usbSelect = $("#usb-select");
  const faceMessage = $("#face-message");
  const usbMessage = $("#usb-message");
  const loginMessage = $("#login-message");
  const accountAuthPanel = $("#account-auth-panel");
  const accountLoginForm = $("#account-login-form");
  const accountSignupForm = $("#account-signup-form");
  const accountMessage = $("#account-message");
  let cameraRunning = false;
  let frameTimer = null;
  let frameRequestRunning = false;
  let enrolledSampleCount = 0;

  async function refreshStatus() {
    const status = await callApi("get_status");
    setPill($("#face-status"), status.face_registered);
    setPill($("#usb-status"), status.usb_registered);
    finishFaceButton.disabled =
      status.face_registered || enrolledSampleCount < 12;
    finishFaceButton.textContent = status.face_registered
      ? "Wajah berhasil didaftarkan"
      : enrolledSampleCount < 12
        ? `Daftarkan wajah — ambil ${12 - enrolledSampleCount} sampel lagi`
        : "Daftarkan wajah sekarang";
    captureButton.disabled = status.face_registered || !cameraRunning;
    registerUsbButton.disabled = status.usb_registered || !usbSelect.value;
    registerUsbButton.textContent = status.usb_registered
      ? "USB berhasil didaftarkan"
      : "Daftarkan USB sebagai kunci";
    unlockButton.disabled = !(status.face_registered && status.usb_registered);

    if (status.face_registered && status.usb_registered) {
      guideClosure("Kedua kunci sudah terdaftar! Sambungkan USB, aktifkan webcam, lalu tekan Verifikasi dan buka.");
    } else if (status.face_registered) {
      guideClosure("Wajah sudah terdaftar. Sekarang sambungkan USB, tekan tombol ↻, pilih flashdisk, lalu daftarkan sebagai kunci.");
    } else if (status.usb_registered) {
      guideClosure("USB sudah terdaftar. Aktifkan webcam, ambil 12 sampel wajah, lalu tekan Daftarkan wajah sekarang.");
    } else {
      guideClosure("Halo! Saya Closure, pemandu brankas ini. Mulai dengan mengaktifkan webcam dan mengambil 12 sampel wajah.");
    }
    return status;
  }

  function setAccountMode(mode, hasAccounts) {
    const signingUp = mode === "signup";
    accountLoginForm.hidden = signingUp;
    accountSignupForm.hidden = !signingUp;
    $("#account-login-mode").classList.toggle("is-selected", !signingUp);
    $("#account-signup-mode").classList.toggle("is-selected", signingUp);
    $("#account-auth-title").textContent = signingUp
      ? "Buat akun baru"
      : "Masuk ke akun";
    $("#account-auth-description").textContent = signingUp
      ? hasAccounts
        ? "Buat akun. Akses ke folder dan file diberikan secara terpisah."
        : "Akun pertama menjadi admin. Anda dapat membuat akun lain setelahnya."
      : "Masuk dengan username dan password akun Anda.";
    $("#account-login-mode").hidden = !hasAccounts;
    $("#account-message").textContent = "";
    $("#account-message").classList.remove("is-error", "is-success");
  }

  async function enterAccountStep() {
    await callApi("complete_hardware_authentication");
    $("#setup-card").hidden = true;
    $(".intro").hidden = true;
    $(".shell").classList.add("account-login-shell");
    $(".access-layout").classList.add("account-auth-layout");
    $("#two-factor-panel").hidden = true;
    accountAuthPanel.hidden = false;
    $("#account-closure-guide").hidden = false;
    const accountState = await callApi("get_account_state");
    setAccountMode(accountState.has_accounts ? "login" : "signup", accountState.has_accounts);
    guideClosure(
      accountState.has_accounts
        ? "USB dan wajah cocok! Sekarang masukkan username dan password akun yang ingin Anda buka."
        : "USB dan wajah cocok! Belum ada akun. Buat akun pertama; akun tersebut akan menjadi admin.",
    );
  }

  async function openDashboard(account, verb) {
    const accountRole = account.is_admin ? "Admin" : "Akun";
    showMessage(
      accountMessage,
      `${verb} sebagai ${account.username}${account.is_admin ? " (admin)" : ""}.`,
      "success",
    );
    guideClosure(`${accountRole} ${account.username} berhasil masuk. Membuka brankas dengan izin akun tersebut.`);
    window.setTimeout(() => window.location.replace("dashboard.html"), 250);
  }

  async function refreshUsbDrives(manualRefresh = false) {
    refreshUsbButton.disabled = true;
    try {
      const drives = await callApi("list_usb_drives");
      usbSelect.replaceChildren();
      if (drives.length === 0) {
        usbSelect.add(new Option("Tidak ada USB removable terdeteksi", ""));
      } else {
        usbSelect.add(new Option("Pilih USB Flashdisk", ""));
        for (const drive of drives) {
          usbSelect.add(new Option(drive.label, drive.id));
        }
      }
      registerUsbButton.disabled = !usbSelect.value;
      showMessage(
        usbMessage,
        drives.length && usbSelect.value
          ? `${usbSelect.selectedOptions[0].textContent} dipilih. Tekan "Daftarkan USB sebagai kunci" untuk melanjutkan.`
          : drives.length
            ? `${drives.length} drive USB ditemukan. Pilih flashdisk yang ingin didaftarkan.`
          : "Sambungkan flashdisk, lalu perbarui daftar.",
        drives.length && usbSelect.value ? "success" : "",
      );
      if (manualRefresh && drives.length && !usbSelect.value) {
        guideClosure("USB terdeteksi! Pilih flashdisk yang ingin dijadikan kunci. Tenang, isinya tidak akan diformat atau dihapus.");
      } else if (manualRefresh && !drives.length) {
        guideClosure("Saya belum melihat USB removable. Sambungkan flashdisk, lalu tekan tombol ↻ untuk mencoba lagi.");
      }
    } catch (error) {
      showMessage(usbMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      refreshUsbButton.disabled = false;
    }
  }

  async function startCamera() {
    cameraButton.disabled = true;
    try {
      const message = await callApi("start_camera");
      cameraRunning = true;
      cameraButton.textContent = "Webcam aktif";
      captureButton.disabled = (await callApi("get_status")).face_registered;
      preview.hidden = false;
      placeholder.hidden = true;
      showMessage(faceMessage, message, "success");
      guideClosure("Webcam aktif. Posisikan wajah di tengah pratinjau, lalu tekan Ambil sampel. Ulangi 12 kali dengan sedikit perubahan sudut.");
      frameTimer = window.setInterval(async () => {
        if (frameRequestRunning) return;
        frameRequestRunning = true;
        try {
          preview.src = await callApi("camera_frame");
        } catch (error) {
          window.clearInterval(frameTimer);
          cameraRunning = false;
          captureButton.disabled = true;
          showMessage(faceMessage, error.message, "error");
          guideClosure(error.message);
        } finally {
          frameRequestRunning = false;
        }
      }, 250);
      return true;
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      guideClosure(error.message);
      cameraButton.disabled = false;
      return false;
    }
  }

  cameraButton.addEventListener("click", startCamera);
  captureButton.addEventListener("click", async () => {
    captureButton.disabled = true;
    try {
      const result = await callApi("capture_face_sample");
      enrolledSampleCount = result.count;
      $("#sample-count").textContent = `${result.count}/${result.required}`;
      $("#sample-progress").style.width =
        `${(result.count / result.required) * 100}%`;
      finishFaceButton.textContent =
        result.count >= result.required
          ? "Daftarkan wajah sekarang"
          : `Daftarkan wajah — ambil ${result.required - result.count} sampel lagi`;
      finishFaceButton.disabled = result.count < result.required;
      showMessage(
        faceMessage,
        `Sampel ${result.count} dari ${result.required} berhasil diambil. Ubah sedikit posisi wajah untuk sampel berikutnya.`,
        "success",
      );
      guideClosure(
        result.count >= result.required
          ? "Sampel wajah lengkap! Tekan Daftarkan wajah sekarang untuk menyimpan pendaftaran."
          : `Sampel ${result.count} dari ${result.required} tersimpan. Ubah sedikit sudut wajah, lalu ambil sampel berikutnya.`,
      );
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      captureButton.disabled =
        !cameraRunning || enrolledSampleCount >= 12;
    }
  });

  finishFaceButton.addEventListener("click", async () => {
    finishFaceButton.disabled = true;
    try {
      const message = await callApi("finish_face_enrollment");
      showMessage(faceMessage, message, "success");
      guideClosure("Wajah berhasil didaftarkan. Sekarang pilih dan daftarkan USB sebagai kunci kedua.");
      await refreshStatus();
    } catch (error) {
      showMessage(faceMessage, error.message, "error");
      guideClosure(error.message);
      finishFaceButton.disabled = false;
    }
  });

  refreshUsbButton.addEventListener("click", () => refreshUsbDrives(true));
  usbSelect.addEventListener("change", () => {
    registerUsbButton.disabled = !usbSelect.value;
    if (usbSelect.value) {
      showMessage(
        usbMessage,
        `${usbSelect.selectedOptions[0].textContent} dipilih. Tekan tombol "Daftarkan USB sebagai kunci" di bawah.`,
        "success",
      );
      guideClosure("Flashdisk sudah dipilih. Tekan Daftarkan USB sebagai kunci; saya akan meminta konfirmasi sebelum membuat file token.");
    }
  });

  registerUsbButton.addEventListener("click", async () => {
    if (!usbSelect.value) return;
    const drive = usbSelect.selectedOptions[0].textContent;
    const accepted = window.confirm(
      `Daftarkan ${drive} sebagai kunci USB?\n\n` +
        "USB TIDAK akan diformat dan file yang sudah ada tidak dihapus. " +
        "Aplikasi hanya membuat satu file token kecil bernama " +
        "USL-USB-KEY.txt di folder utama USB tersebut.",
    );
    if (!accepted) return;

    registerUsbButton.disabled = true;
    try {
      const message = await callApi("register_usb_key", usbSelect.value);
      showMessage(usbMessage, message, "success");
      guideClosure("Kunci USB berhasil didaftarkan. Setelah wajah dan USB berstatus Terdaftar, tekan Verifikasi dan buka.");
      await refreshStatus();
    } catch (error) {
      showMessage(usbMessage, error.message, "error");
      guideClosure(error.message);
      registerUsbButton.disabled = !usbSelect.value;
    }
  });

  unlockButton.addEventListener("click", async () => {
    unlockButton.disabled = true;
    $("#usb-check").textContent = "…";
    $("#face-check").textContent = "…";
    showMessage(loginMessage, "Memeriksa USB Flashdisk…");
    guideClosure("Saya sedang memeriksa token pada USB. Pastikan flashdisk yang didaftarkan terhubung.");
    try {
      if (!cameraRunning && !(await startCamera())) {
        showMessage(loginMessage, "Webcam perlu aktif untuk memverifikasi wajah.", "error");
        guideClosure("Webcam belum siap. Aktifkan kamera agar saya bisa memeriksa wajah Anda.");
        return;
      }
      const usbVerified = await callApi("verify_usb");
      if (!usbVerified) {
        $("#usb-check").textContent = "×";
        $("#usb-check").classList.remove("is-ready");
        $("#face-check").textContent = "—";
        showMessage(
          loginMessage,
          "Kunci USB tidak ditemukan. Sambungkan flashdisk yang telah didaftarkan.",
          "error",
        );
        guideClosure("Token USB belum cocok. Sambungkan flashdisk yang didaftarkan, lalu coba lagi.");
        return;
      }
      $("#usb-check").textContent = "✓";
      $("#usb-check").classList.add("is-ready");
      showMessage(loginMessage, "USB cocok. Memeriksa wajah melalui webcam…");
      guideClosure("USB cocok! Sekarang lihat ke kamera agar saya dapat memeriksa wajah Anda.");

      const faceResult = await callApi("verify_face");
      $("#face-check").textContent = faceResult.verified ? "✓" : "×";
      $("#face-check").classList.toggle("is-ready", faceResult.verified);
      if (!faceResult.verified) {
        showMessage(loginMessage, faceResult.message, "error");
        guideClosure("Wajah belum cocok. Atur pencahayaan, lihat ke kamera, lalu coba verifikasi lagi.");
        return;
      }

      await enterAccountStep();
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      if ($("#two-factor-panel").hidden) {
        accountAuthPanel.hidden = false;
      } else {
        $("#face-check").textContent = "×";
        showMessage(loginMessage, error.message, "error");
      }
      guideClosure(error.message);
    } finally {
      unlockButton.disabled = false;
    }
  });

  $("#account-login-mode").addEventListener("click", () => {
    setAccountMode("login", true);
  });
  $("#account-signup-mode").addEventListener("click", () => {
    setAccountMode("signup", true);
  });

  accountLoginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = accountLoginForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      const account = await callApi(
        "login_account",
        $("#login-username").value,
        $("#login-password").value,
      );
      await openDashboard(account, "Login");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      submitButton.disabled = false;
    }
  });

  accountSignupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = accountSignupForm.querySelector('button[type="submit"]');
    const password = $("#signup-password").value;
    if (password !== $("#signup-confirm-password").value) {
      showMessage(accountMessage, "Konfirmasi password tidak sama.", "error");
      guideClosure("Konfirmasi password belum sama. Periksa kembali kedua kolom password.");
      return;
    }

    submitButton.disabled = true;
    try {
      const account = await callApi(
        "create_account",
        $("#signup-username").value,
        password,
      );
      await openDashboard(account, "Akun dibuat");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
      guideClosure(error.message);
    } finally {
      submitButton.disabled = false;
    }
  });

  try {
    await refreshStatus();
    await refreshUsbDrives();
  } catch (error) {
    showMessage(loginMessage, error.message, "error");
    guideClosure(error.message);
  }
}

async function initializeDashboard() {
  try {
    if (!(await callApi("is_authenticated"))) {
      window.location.replace("index.html");
      return;
    }
  } catch (error) {
    window.alert(error.message);
    guideClosure(error.message);
    window.location.replace("index.html");
    return;
  }

  const account = await callApi("get_current_account");
  $("#active-username").textContent =
    `${account.username}${account.is_admin ? " · ADMIN" : ""}`;
  guideClosure(
    `Selamat datang, ${account.username}! Anda hanya akan melihat folder dan file yang dimiliki atau dibagikan khusus ke akun ini.`,
  );

  const resourceList = $("#resource-list");
  const vaultMessage = $("#vault-message");
  const uploadInput = $("#upload-file-input");
  const replaceInput = $("#replace-file-input");
  const shareDialog = $("#share-dialog");
  let currentParentId = null;
  let currentFolderName = "";
  let itemToReplace = null;
  let itemToShare = null;

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        const result = reader.result;
        if (typeof result !== "string" || !result.includes(",")) {
          reject(new Error("File gagal dibaca."));
          return;
        }
        resolve(result.slice(result.indexOf(",") + 1));
      });
      reader.addEventListener("error", () => reject(new Error("File gagal dibaca.")));
      reader.readAsDataURL(file);
    });
  }

  function makeButton(label, callback, variant = "button-secondary") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `button ${variant}`;
    button.textContent = label;
    button.addEventListener("click", callback);
    return button;
  }

  function showVaultError(error) {
    showMessage(vaultMessage, error.message, "error");
    guideClosure(error.message);
  }

  async function loadVault() {
    resourceList.replaceChildren();
    $("#vault-location").textContent = currentParentId
      ? currentFolderName
      : "Folder utama";
    $("#vault-back-button").hidden = !currentParentId;

    try {
      const canCreate = await callApi("can_create_in", currentParentId);
      $("#create-folder-button").disabled = !canCreate;
      uploadInput.disabled = !canCreate;
      $("#vault-guidance").textContent = canCreate
        ? "Anda dapat menambahkan item di sini. Akses item lain tetap mengikuti izin masing-masing."
        : "Akun ini dapat melihat item di folder ini tetapi belum memiliki izin untuk membuat item baru.";

      const resources = await callApi("list_resources", currentParentId);
      if (resources.length === 0) {
        const empty = document.createElement("div");
        empty.className = "resource-empty";
        empty.textContent = "Belum ada folder atau file yang dapat diakses di lokasi ini.";
        resourceList.append(empty);
      }

      for (const resource of resources) {
        const row = document.createElement("article");
        row.className = "resource-row";
        const symbol = document.createElement("span");
        symbol.className = "resource-symbol";
        symbol.textContent = resource.kind === "folder" ? "▰" : "▧";
        symbol.setAttribute("aria-hidden", "true");

        const name = document.createElement("div");
        name.className = "resource-name";
        name.append(document.createTextNode(resource.name));
        const owner = document.createElement("small");
        owner.className = "resource-owner";
        owner.textContent = resource.is_owner
          ? "Milik Anda"
          : "Dibagikan kepada Anda";
        name.append(owner);

        const actions = document.createElement("div");
        actions.className = "resource-actions";
        if (resource.kind === "folder") {
          actions.append(
            makeButton("Buka", async () => {
              currentParentId = resource.id;
              currentFolderName = resource.name;
              await loadVault();
            }, "button-primary"),
          );
        } else {
          actions.append(
            makeButton("Lihat / unduh", async () => {
              try {
                const file = await callApi("read_resource", resource.id);
                const binary = atob(file.content_base64);
                const bytes = Uint8Array.from(binary, (character) =>
                  character.charCodeAt(0),
                );
                const blob = new Blob([bytes], { type: file.content_type });
                const isText =
                  file.content_type.startsWith("text/") ||
                  /^(application\/(json|xml|javascript))$/.test(file.content_type) ||
                  /\.(csv|json|md|txt|xml|yaml|yml)$/i.test(file.name);
                if (isText) {
                  $("#preview-title").textContent = file.name;
                  $("#preview-content").textContent = new TextDecoder().decode(bytes);
                  $("#preview-dialog").showModal();
                } else {
                  const objectUrl = URL.createObjectURL(blob);
                  const download = document.createElement("a");
                  download.href = objectUrl;
                  download.download = file.name;
                  download.click();
                  URL.revokeObjectURL(objectUrl);
                }
              } catch (error) {
                showVaultError(error);
              }
            }),
          );
        }

        if (resource.can_update) {
          actions.append(
            makeButton("Ubah", async () => {
              if (resource.kind === "file") {
                itemToReplace = resource;
                replaceInput.click();
                return;
              }
              const nextName = window.prompt("Nama baru:", resource.name);
              if (!nextName || nextName === resource.name) return;
              try {
                await callApi("update_resource", resource.id, nextName);
                showMessage(vaultMessage, "Nama folder berhasil diperbarui.", "success");
                await loadVault();
              } catch (error) {
                showVaultError(error);
              }
            }),
          );
        }

        if (resource.can_manage) {
          actions.append(
            makeButton("Atur akses", async () => openSharingDialog(resource)),
          );
        }
        row.append(symbol, name, actions);
        resourceList.append(row);
      }
      showMessage(vaultMessage, `${resources.length} item dapat diakses di sini.`);
    } catch (error) {
      showVaultError(error);
    }
  }

  async function openSharingDialog(resource) {
    itemToShare = resource;
    $("#share-dialog-title").textContent = `Izin: ${resource.name}`;
    $("#share-create-option").hidden = resource.kind !== "folder";
    $("#share-message").textContent = "";
    try {
      const result = await callApi("list_accounts_for_sharing", resource.id);
      const select = $("#share-account-select");
      select.replaceChildren();
      for (const target of result.accounts) {
        select.add(new Option(target.username, String(target.id)));
      }
      if (result.accounts.length === 0) {
        showMessage($("#share-message"), "Belum ada akun lain yang dapat diberi izin.");
        $("#share-read").checked = false;
        $("#share-create").checked = false;
        $("#share-update").checked = false;
        shareDialog.showModal();
        return;
      }

      function updateSelectedAccountPermissions() {
        const target = result.accounts.find(
          (entry) => String(entry.id) === select.value,
        );
        const permissions = target?.permissions ?? {};
        $("#share-read").checked = Boolean(permissions.read);
        $("#share-create").checked = Boolean(permissions.create);
        $("#share-update").checked = Boolean(permissions.update);
      }
      select.onchange = updateSelectedAccountPermissions;
      updateSelectedAccountPermissions();
      shareDialog.showModal();
    } catch (error) {
      showVaultError(error);
    }
  }

  $("#share-update").addEventListener("change", (event) => {
    if (event.target.checked) $("#share-read").checked = true;
  });
  $("#share-create").addEventListener("change", (event) => {
    if (event.target.checked) $("#share-read").checked = true;
  });
  $("#save-sharing-button").addEventListener("click", async () => {
    const select = $("#share-account-select");
    if (!itemToShare || !select.value) {
      showMessage($("#share-message"), "Pilih akun yang akan diberi izin.", "error");
      return;
    }
    const saveButton = $("#save-sharing-button");
    saveButton.disabled = true;
    try {
      await callApi(
        "set_resource_permissions",
        itemToShare.id,
        Number(select.value),
        $("#share-create").checked,
        $("#share-read").checked,
        $("#share-update").checked,
      );
      showMessage($("#share-message"), "Izin item berhasil disimpan.", "success");
      guideClosure(`Izin untuk ${itemToShare.name} sudah diperbarui.`);
      window.setTimeout(() => shareDialog.close(), 450);
      await loadVault();
    } catch (error) {
      showMessage($("#share-message"), error.message, "error");
      guideClosure(error.message);
    } finally {
      saveButton.disabled = false;
    }
  });

  $("#create-folder-button").addEventListener("click", async () => {
    const name = window.prompt("Nama folder baru:");
    if (!name) return;
    try {
      await callApi("create_resource", name, "folder", currentParentId);
      showMessage(vaultMessage, "Folder berhasil dibuat.", "success");
      guideClosure(`Folder ${name} berhasil dibuat. Atur izin folder jika ingin membagikannya.`);
      await loadVault();
    } catch (error) {
      showVaultError(error);
    }
  });

  uploadInput.addEventListener("change", async () => {
    const file = uploadInput.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      showVaultError(new Error("Ukuran file maksimal 10 MiB."));
      uploadInput.value = "";
      return;
    }
    try {
      const content = await readFileAsBase64(file);
      await callApi(
        "create_resource",
        file.name,
        "file",
        currentParentId,
        content,
        file.type || "application/octet-stream",
      );
      showMessage(vaultMessage, `${file.name} berhasil disimpan.`, "success");
      guideClosure(`File ${file.name} berhasil disimpan. Gunakan Atur akses untuk memilih akun yang boleh melihat atau mengubahnya.`);
      await loadVault();
    } catch (error) {
      showVaultError(error);
    } finally {
      uploadInput.value = "";
    }
  });

  replaceInput.addEventListener("change", async () => {
    const file = replaceInput.files?.[0];
    const resource = itemToReplace;
    if (!file || !resource) return;
    if (file.size > 10 * 1024 * 1024) {
      showVaultError(new Error("Ukuran file maksimal 10 MiB."));
      replaceInput.value = "";
      return;
    }
    try {
      const content = await readFileAsBase64(file);
      await callApi(
        "update_resource",
        resource.id,
        file.name,
        content,
        file.type || "application/octet-stream",
      );
      showMessage(vaultMessage, `${file.name} berhasil diperbarui.`, "success");
      guideClosure(`File ${file.name} berhasil diperbarui.`);
      await loadVault();
    } catch (error) {
      showVaultError(error);
    } finally {
      itemToReplace = null;
      replaceInput.value = "";
    }
  });

  $("#vault-back-button").addEventListener("click", async () => {
    currentParentId = null;
    currentFolderName = "";
    await loadVault();
  });

  $("#logout-button").addEventListener("click", async () => {
    try {
      await callApi("logout");
      window.location.replace("index.html");
    } catch (error) {
      window.alert(error.message);
      guideClosure(error.message);
    }
  });

  await loadVault();
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "access") initializeAccessPage();
  if (page === "dashboard") initializeDashboard();
});