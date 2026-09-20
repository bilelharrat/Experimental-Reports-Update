<script setup>
// Account administration: approve a registration and assign its role in
// the same act, disable an account, and mint the reset link an admin
// carries to someone by hand. Server-enforced — every call here needs
// `users:manage`, which only admin has — so this screen is a convenience,
// never the boundary.
import { computed, onMounted, ref } from "vue";
import { Ban, Check, KeyRound, Loader2 } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import { api } from "../api.js";
import { useT } from "../i18n.js";

const t = useT();

const accounts = ref([]);
const roles = ref([]);
const loading = ref(true);
const loadError = ref(null);
const busyEmail = ref(null);
const chosenRole = ref({});
const notice = ref(null);

const pendingCount = computed(
  () => accounts.value.filter((a) => a.status === "pending").length,
);

const STATUS_LABEL = {
  pending: "accounts.status_pending",
  active: "accounts.status_active",
  disabled: "accounts.status_disabled",
};

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    const res = await api.listAccounts();
    accounts.value = res?.accounts || [];
    roles.value = res?.roles || [];
  } catch (e) {
    loadError.value = e?.detail || e?.message || t("accounts.load_failed");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

// One server call serves three cases — approving a pending account,
// re-enabling a disabled one, and changing an active one's role — because
// the server's "approve" is "make active with this role".
async function approve(account) {
  const role = chosenRole.value[account.email];
  if (!role) return;
  busyEmail.value = account.email;
  notice.value = null;
  try {
    await api.approveAccount(account.email, role);
    await load();
  } catch (e) {
    loadError.value = e?.detail || e?.message || t("auth.unknown_error");
  } finally {
    busyEmail.value = null;
  }
}

async function disable(account) {
  busyEmail.value = account.email;
  notice.value = null;
  try {
    await api.disableAccount(account.email);
    await load();
  } catch (e) {
    loadError.value = e?.detail || e?.message || t("auth.unknown_error");
  } finally {
    busyEmail.value = null;
  }
}

async function resetLink(account) {
  busyEmail.value = account.email;
  notice.value = null;
  try {
    const res = await api.mintResetLink(account.email);
    const url = `${window.location.origin}${import.meta.env.BASE_URL.replace(/\/$/, "")}${res.path}`;
    try {
      await navigator.clipboard.writeText(url);
      notice.value = t("accounts.reset_link_copied", {
        hours: res.expires_in_hours,
      });
    } catch {
      // Clipboard refused (insecure origin, permissions): show the link so
      // it can still be copied by hand rather than losing it — it is
      // minted and the store keeps only its hash.
      notice.value = url;
    }
    await load();
  } catch (e) {
    loadError.value = e?.detail || e?.message || t("auth.unknown_error");
  } finally {
    busyEmail.value = null;
  }
}

function shortDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}
</script>

<template>
  <div class="page">
    <PageHeader :title="t('accounts.title')" :subtitle="t('accounts.subtitle')">
      <template #actions>
        <span v-if="pendingCount" class="chip bg-accent/10 text-accent-ink">
          {{ t("accounts.pending_count", { count: pendingCount }) }}
        </span>
      </template>
    </PageHeader>

    <p v-if="notice" class="glass-card mt-4 break-all rounded-card p-3 text-footnote text-ink-secondary" data-testid="accounts-notice">
      {{ notice }}
    </p>

    <p v-if="loadError" class="glass-card mt-4 rounded-card p-3 text-footnote text-danger" data-testid="accounts-error">
      {{ loadError }}
    </p>

    <div v-if="loading" class="glass-card mt-4 flex items-center gap-2 rounded-card p-4 text-footnote text-ink-subtle">
      <Loader2 class="h-4 w-4 animate-spin" />
    </div>

    <p v-else-if="!accounts.length" class="glass-card mt-4 rounded-card p-4 text-footnote text-ink-subtle">
      {{ t("accounts.none") }}
    </p>

    <div v-else class="glass-card mt-4 overflow-x-auto rounded-card">
      <table class="w-full text-left text-footnote">
        <thead class="text-ink-subtle">
          <tr>
            <th class="px-4 py-2 font-medium">{{ t("accounts.col_email") }}</th>
            <th class="px-4 py-2 font-medium">{{ t("accounts.col_status") }}</th>
            <th class="px-4 py-2 font-medium">{{ t("accounts.col_role") }}</th>
            <th class="px-4 py-2 font-medium">{{ t("accounts.col_requested") }}</th>
            <th class="px-4 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="account in accounts"
            :key="account.email"
            class="border-t border-subtle align-middle"
            :data-testid="`account-${account.status}`"
          >
            <td class="px-4 py-2.5 text-ink-primary">
              {{ account.email }}
              <span v-if="account.reset_requested_at" class="ml-1.5 text-caption1 text-warning">
                {{ t("accounts.reset_requested") }}
              </span>
            </td>
            <td class="px-4 py-2.5">{{ t(STATUS_LABEL[account.status] || "accounts.status_active") }}</td>
            <td class="px-4 py-2.5">{{ account.role || "—" }}</td>
            <td class="px-4 py-2.5 text-ink-subtle">{{ shortDate(account.created_at) }}</td>
            <td class="px-4 py-2.5">
              <div class="flex items-center justify-end gap-2">
                <select
                  v-model="chosenRole[account.email]"
                  class="field w-36"
                  :aria-label="t('accounts.choose_role')"
                >
                  <option value="">{{ t("accounts.choose_role") }}</option>
                  <option v-for="role in roles" :key="role" :value="role">{{ role }}</option>
                </select>
                <button
                  type="button"
                  :class="account.status === 'active' ? 'btn-bordered btn-sm' : 'btn-filled btn-sm'"
                  :disabled="!chosenRole[account.email] || busyEmail === account.email"
                  :data-testid="`account-action-${account.status}`"
                  @click="approve(account)"
                >
                  <Check class="h-3.5 w-3.5" />
                  <span>
                    {{
                      account.status === "pending"
                        ? t("accounts.approve")
                        : account.status === "disabled"
                          ? t("accounts.enable")
                          : t("accounts.set_role")
                    }}
                  </span>
                </button>

                <button
                  type="button"
                  class="btn-bordered btn-sm"
                  :disabled="busyEmail === account.email"
                  @click="resetLink(account)"
                >
                  <KeyRound class="h-3.5 w-3.5" />
                  <span>{{ t("accounts.reset_link") }}</span>
                </button>

                <button
                  v-if="account.status === 'active'"
                  type="button"
                  class="btn-bordered btn-sm"
                  :disabled="busyEmail === account.email"
                  @click="disable(account)"
                >
                  <Ban class="h-3.5 w-3.5" />
                  <span>{{ t("accounts.disable") }}</span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
