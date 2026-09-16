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
});
