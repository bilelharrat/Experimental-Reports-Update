export function trackingActionLabel(action, t) {
  if (!action?.kind) return "";
  const key = `tracking.action_${action.kind}`;
  const label = t(key);
  return label === key ? action.label : label;
}

export function trackingAttentionLabel(item, t) {
  const count = Number(item?.count) || 0;
  const singular = `tracking.attn_${item?.kind}_one`;
  if (count === 1) {
    const one = t(singular);
    if (one !== singular) return one;
  }
  const key = `tracking.attn_${item?.kind}`;
  const label = t(key, { count });
  return label === key ? item?.label : label;
}
