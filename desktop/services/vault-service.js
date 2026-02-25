'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { scryptSync } = require('node:crypto');
const { safeStorage } = require('electron');

class DesktopVaultService {
  constructor({ userDataPath, log } = {}) {
    this.userDataPath = userDataPath || process.cwd();
    this.log = typeof log === 'function' ? log : () => {};
    this.vaultFilePath = path.join(this.userDataPath, 'local-vault.json');
    this.passphrase = null;
    this.mediaEncryptionKeyBase64 = null;
    this.state = {
      initialized: false,
      unlocked: false,
      vaultEpoch: 1,
      safeStorageAvailable: false,
      lastError: null,
    };
  }

  isSafeStorageAvailable() {
    try {
      return Boolean(safeStorage?.isEncryptionAvailable?.());
    } catch {
      return false;
    }
  }

  readVaultFile() {
    try {
      if (!fs.existsSync(this.vaultFilePath)) {
        return null;
      }
      const raw = fs.readFileSync(this.vaultFilePath, 'utf8');
      if (!raw.trim()) {
        return null;
      }
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (error) {
      this.state.lastError = `vault_read_failed:${String(error)}`;
      return null;
    }
  }

  writeVaultFile(payload) {
    try {
      fs.mkdirSync(path.dirname(this.vaultFilePath), { recursive: true });
      fs.writeFileSync(this.vaultFilePath, JSON.stringify(payload, null, 2), 'utf8');
      return true;
    } catch (error) {
      this.state.lastError = `vault_write_failed:${String(error)}`;
      return false;
    }
  }

  deriveMediaEncryptionKey(passphrase, vaultEpoch) {
    const normalizedPassphrase = String(passphrase || '').trim();
    const epoch = Number(vaultEpoch) > 0 ? Math.floor(Number(vaultEpoch)) : 1;
    const salt = `revisbali-vault-epoch:${epoch}`;
    const keyBuffer = scryptSync(normalizedPassphrase, salt, 32);
    return keyBuffer.toString('base64');
  }

  setUnlockedState({ passphrase, vaultEpoch }) {
    this.passphrase = String(passphrase || '');
    this.mediaEncryptionKeyBase64 = this.deriveMediaEncryptionKey(this.passphrase, vaultEpoch);
    this.state.vaultEpoch = Number(vaultEpoch) > 0 ? Math.floor(Number(vaultEpoch)) : 1;
    this.state.initialized = true;
    this.state.unlocked = true;
    this.state.lastError = null;
  }

  clearUnlockedState() {
    this.passphrase = null;
    this.mediaEncryptionKeyBase64 = null;
    this.state.unlocked = false;
  }

  initialize({ initialVaultEpoch = 1 } = {}) {
    const safeStorageAvailable = this.isSafeStorageAvailable();
    this.state.safeStorageAvailable = safeStorageAvailable;
    this.state.initialized = true;

    const parsedEpoch =
      Number(initialVaultEpoch) > 0 ? Math.floor(Number(initialVaultEpoch)) : 1;
    this.state.vaultEpoch = parsedEpoch;

    const persisted = this.readVaultFile();
    if (!persisted) {
      this.writeVaultFile({
        vaultEpoch: parsedEpoch,
        encryptedPassphrase: '',
        updatedAt: new Date().toISOString(),
      });
      return this.getStatus();
    }

    const persistedEpoch =
      Number(persisted.vaultEpoch) > 0 ? Math.floor(Number(persisted.vaultEpoch)) : parsedEpoch;
    this.state.vaultEpoch = persistedEpoch;

    if (!safeStorageAvailable) {
      this.state.lastError = 'safe_storage_unavailable';
      return this.getStatus();
    }

    const encryptedPassphrase = String(persisted.encryptedPassphrase || '').trim();
    if (!encryptedPassphrase) {
      return this.getStatus();
    }

    try {
      const decryptedPassphrase = safeStorage.decryptString(
        Buffer.from(encryptedPassphrase, 'base64'),
      );
      if (decryptedPassphrase && decryptedPassphrase.trim()) {
        this.setUnlockedState({
          passphrase: decryptedPassphrase,
          vaultEpoch: this.state.vaultEpoch,
        });
      }
    } catch (error) {
      this.state.lastError = `vault_auto_unlock_failed:${String(error)}`;
      this.clearUnlockedState();
    }

    return this.getStatus();
  }

  persistEncryptedPassphrase(passphrase) {
    if (!this.state.safeStorageAvailable) {
      this.state.lastError = 'safe_storage_unavailable';
      return false;
    }

    try {
      const encrypted = safeStorage.encryptString(String(passphrase || '').trim());
      return this.writeVaultFile({
        vaultEpoch: this.state.vaultEpoch,
        encryptedPassphrase: encrypted.toString('base64'),
        updatedAt: new Date().toISOString(),
      });
    } catch (error) {
      this.state.lastError = `vault_encrypt_failed:${String(error)}`;
      return false;
    }
  }

  unlock(passphrase) {
    const normalizedPassphrase = String(passphrase || '').trim();
    if (!normalizedPassphrase) {
      this.state.lastError = 'empty_passphrase';
      return this.getStatus();
    }

    this.setUnlockedState({
      passphrase: normalizedPassphrase,
      vaultEpoch: this.state.vaultEpoch,
    });
    this.persistEncryptedPassphrase(normalizedPassphrase);
    return this.getStatus();
  }

  lock({ clearPersisted = false } = {}) {
    this.clearUnlockedState();
    if (clearPersisted) {
      this.writeVaultFile({
        vaultEpoch: this.state.vaultEpoch,
        encryptedPassphrase: '',
        updatedAt: new Date().toISOString(),
      });
    }
    return this.getStatus();
  }

  applyVaultEpoch(vaultEpoch) {
    const parsedEpoch = Number(vaultEpoch) > 0 ? Math.floor(Number(vaultEpoch)) : 1;
    if (parsedEpoch === this.state.vaultEpoch) {
      return this.getStatus();
    }

    this.state.vaultEpoch = parsedEpoch;
    this.lock({ clearPersisted: true });
    this.writeVaultFile({
      vaultEpoch: parsedEpoch,
      encryptedPassphrase: '',
      updatedAt: new Date().toISOString(),
    });
    return this.getStatus();
  }

  getMediaEncryptionKey() {
    return this.mediaEncryptionKeyBase64;
  }

  getStatus() {
    return {
      initialized: Boolean(this.state.initialized),
      unlocked: Boolean(this.state.unlocked),
      vaultEpoch: Number(this.state.vaultEpoch) || 1,
      safeStorageAvailable: Boolean(this.state.safeStorageAvailable),
      lastError: this.state.lastError || null,
    };
  }
}

module.exports = {
  DesktopVaultService,
};
