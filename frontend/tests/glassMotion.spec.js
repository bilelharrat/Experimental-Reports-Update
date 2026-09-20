import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { mount } from "@vue/test-utils";
import { useGlider } from "../src/glassMotion.js";

// The sidebar's company list renders behind a `v-else` that stays empty until
// companies load, so the glider's container arrives after the composable
// mounts. Let a few frames pass so the MutationObserver callback and the
// rAF-scheduled measure both run.
async function settle() {
  for (let i = 0; i < 4; i += 1) {
    await nextTick();
    await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  }
}

const Harness = {
  props: { ready: Boolean, selected: Boolean },
  setup(props) {
    const containerRef = ref(null);
    const { visible } = useGlider(containerRef, ".row.is-active");
    return { containerRef, visible, props };
  },
  template: `
    <div v-if="ready" ref="containerRef">
      <a class="row" :class="selected ? 'is-active' : ''">Row</a>
    </div>
  `,
};

describe("useGlider", () => {
  it("tracks a container that mounts after the composable does", async () => {
    const wrapper = mount(Harness, {
      props: { ready: false, selected: true },
      attachTo: document.body,
    });
    await settle();
    expect(wrapper.vm.visible).toBe(false);

    await wrapper.setProps({ ready: true });
    await settle();
    expect(wrapper.vm.visible).toBe(true);

    wrapper.unmount();
  });

  it("hides the pill when the selected row goes inactive", async () => {
    // Mount empty first, the way the sidebar does before companies load.
    const wrapper = mount(Harness, {
      props: { ready: false, selected: true },
      attachTo: document.body,
    });
    await settle();
    await wrapper.setProps({ ready: true });
    await settle();
    expect(wrapper.vm.visible).toBe(true);

    // Navigating away drops `router-link-active` from the row; the pill must
    // not stay parked on a company the sidebar no longer has selected.
    await wrapper.setProps({ selected: false });
    await settle();
    expect(wrapper.vm.visible).toBe(false);

    wrapper.unmount();
  });

  it("hides the pill when the container itself goes away", async () => {
    const wrapper = mount(Harness, {
      props: { ready: true, selected: true },
      attachTo: document.body,
    });
    await settle();
    expect(wrapper.vm.visible).toBe(true);

    await wrapper.setProps({ ready: false });
    await settle();
    expect(wrapper.vm.visible).toBe(false);

    wrapper.unmount();
  });
});
