import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import LoginView from "../src/views/LoginView.vue";
import * as auth from "../src/auth.js";

const mockPush = vi.fn();
const mockReplace = vi.fn();
const mockBack = vi.fn();

vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    back: mockBack,
  }),
}));

vi.mock("../src/auth.js", () => ({
  signIn: vi.fn(),
  isAnonDev: vi.fn(() => false),
}));

vi.mock("../src/api.js", () => ({
  api: {
    register: vi.fn(),
    requestPasswordReset: vi.fn(),
  },
}));

import { api } from "../src/api.js";

describe("LoginView Summit Glass Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the Berkeley Summit House brand hero, title, subtitle and node pill", () => {
    const wrapper = mount(LoginView);
    expect(wrapper.text()).toContain("BSH Research Center");
    expect(wrapper.text()).toContain("Institutional Terminal · Berkeley Summit House");
    expect(wrapper.find(".login-tile").exists()).toBe(true);
    expect(wrapper.find("input[type='text']").exists()).toBe(true);
    expect(wrapper.find("input[type='password']").exists()).toBe(true);
  });

  it("toggles password visibility with the eye button", async () => {
    const wrapper = mount(LoginView);
    const passwordInput = wrapper.find("input[type='password']");
    expect(passwordInput.exists()).toBe(true);

    const toggleBtn = wrapper.find("button[aria-label='Show password']");
    expect(toggleBtn.exists()).toBe(true);
    await toggleBtn.trigger("click");

    expect(wrapper.findAll("input[type='text']").length).toBe(2);
  });

  it("submits institutional credentials and redirects on success", async () => {
    vi.mocked(auth.signIn).mockResolvedValueOnce({ token: "test-token" });
    const wrapper = mount(LoginView);

    await wrapper.find("input[type='text']").setValue("trader@berkeleysummithouse.com");
    await wrapper.find("input[type='password']").setValue("securepassword");

    const submitBtn = wrapper.find("button[type='submit']");
    expect(submitBtn.text()).toContain("Sign In to Terminal");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();

    expect(auth.signIn).toHaveBeenCalledWith("trader@berkeleysummithouse.com", "securepassword");
    expect(mockReplace).toHaveBeenCalledWith("/");
  });

  it("displays error banner on failure", async () => {
    vi.mocked(auth.signIn).mockRejectedValueOnce({ status: 401 });
    const wrapper = mount(LoginView);

    await wrapper.find("input[type='text']").setValue("invalid@bsh.com");
    await wrapper.find("input[type='password']").setValue("wrong");

    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();

    expect(wrapper.text()).toContain("Invalid email or password");
  });

  it("sends a must_reset sign-in to the password screen and nowhere else", async () => {
    vi.mocked(auth.signIn).mockResolvedValueOnce({ token: "t", must_reset: true });
    const wrapper = mount(LoginView);
    await wrapper.find("input[type='text']").setValue("robert@bshventures.com");
    await wrapper.find("input[type='password']").setValue("correct-horse-battery");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();
    expect(mockReplace).toHaveBeenCalledWith({ name: "change-password" });
  });

  it("requests access from the sign-up mode and shows the pending panel", async () => {
    vi.mocked(api.register).mockResolvedValueOnce({ status: "pending" });
    const wrapper = mount(LoginView);
    const toSignUp = wrapper.findAll("button").find((b) => /need an account/i.test(b.text()));
    await toSignUp.trigger("click");
    expect(wrapper.text()).toContain("Create account");

    await wrapper.find("input[type='text']").setValue("newcomer@example.com");
    const passwords = wrapper.findAll("input[type='password']");
    expect(passwords.length).toBe(2);
    await passwords[0].setValue("correct-horse-battery");
    await passwords[1].setValue("correct-horse-battery");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();

    expect(api.register).toHaveBeenCalledWith("newcomer@example.com", "correct-horse-battery");
    expect(wrapper.find("[data-testid='auth-notice']").text()).toContain("Request received");
    expect(auth.signIn).not.toHaveBeenCalled();
  });

  it("refuses a sign-up whose passwords differ before calling the server", async () => {
    const wrapper = mount(LoginView);
    await wrapper.findAll("button").find((b) => /need an account/i.test(b.text())).trigger("click");
    await wrapper.find("input[type='text']").setValue("newcomer@example.com");
    const passwords = wrapper.findAll("input[type='password']");
    await passwords[0].setValue("correct-horse-battery");
    await passwords[1].setValue("something-else-entirely");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();
    expect(api.register).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("do not match");
  });

  it("asks for a reset from the forgot mode and says the same thing either way", async () => {
    vi.mocked(api.requestPasswordReset).mockResolvedValueOnce({ status: "requested" });
    const wrapper = mount(LoginView);
    await wrapper.findAll("button").find((b) => /forgot password/i.test(b.text())).trigger("click");
    // No password field in this mode: only the address is asked for.
    expect(wrapper.find("input[type='password']").exists()).toBe(false);
    await wrapper.find("input[type='text']").setValue("someone@example.com");
    await wrapper.find("form").trigger("submit.prevent");
    await flushPromises();
    expect(api.requestPasswordReset).toHaveBeenCalledWith("someone@example.com");
    expect(wrapper.find("[data-testid='auth-notice']").text()).toContain("Request sent");
  });
});
