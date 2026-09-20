import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ChangePasswordView from "../src/views/ChangePasswordView.vue";

const mockReplace = vi.fn();
vi.mock("vue-router", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

// The factory is hoisted above every import, so it builds its own refs.
vi.mock("../src/auth.js", async () => {
  const { ref } = await import("vue");
  return {
    adoptSession: vi.fn(async (s) => s),
    mustResetPassword: ref(false),
    sessionEmail: ref("robert@bshventures.com"),
  };
});

vi.mock("../src/api.js", () => ({
  api: { changePassword: vi.fn() },
}));

import { api } from "../src/api.js";
import * as auth from "../src/auth.js";

function fill(wrapper, current, next, confirm) {
  const inputs = wrapper.findAll("input[type='password']");
  return Promise.all([
    inputs[0].setValue(current),
    inputs[1].setValue(next),
    inputs[2].setValue(confirm),
  ]);
}

describe("ChangePasswordView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.mustResetPassword.value = false;
  });

  it("says why it is here when the server is forcing the change", () => {
    auth.mustResetPassword.value = true;
    const wrapper = mount(ChangePasswordView);
    expect(wrapper.find("[data-testid='change-password-reason']").text()).toContain(
      "needs a new password",
    );
  });

  it("changes the password, takes up the fresh session, and goes home", async () => {
    vi.mocked(api.changePassword).mockResolvedValueOnce({ token: "fresh", must_reset: false });
    const wrapper = mount(ChangePasswordView);
    await fill(wrapper, "old-password-here", "new-password-here", "new-password-here");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();
    expect(api.changePassword).toHaveBeenCalledWith("old-password-here", "new-password-here");
    expect(auth.adoptSession).toHaveBeenCalledWith({ token: "fresh", must_reset: false });
    expect(mockReplace).toHaveBeenCalled();
  });

  it("refuses mismatched passwords before calling the server", async () => {
    const wrapper = mount(ChangePasswordView);
    await fill(wrapper, "old-password-here", "new-password-here", "different-one-here");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();
    expect(api.changePassword).not.toHaveBeenCalled();
    expect(wrapper.find("[data-testid='change-password-error']").text()).toContain("do not match");
  });

  it("shows the server's reason when the current password is wrong", async () => {
    vi.mocked(api.changePassword).mockRejectedValueOnce({ status: 403, detail: "Current password is incorrect" });
    const wrapper = mount(ChangePasswordView);
    await fill(wrapper, "wrong-password-here", "new-password-here", "new-password-here");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();
    expect(wrapper.find("[data-testid='change-password-error']").text()).toContain("Current password is incorrect");
    expect(auth.adoptSession).not.toHaveBeenCalled();
  });
});
