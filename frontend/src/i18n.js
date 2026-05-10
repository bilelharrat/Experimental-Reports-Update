// Lightweight in-app i18n. No vue-i18n dependency — small dictionary plus a
// `t(key)` helper that reads the global appLanguage ref from state.js.
//
// Adding a string: pick a stable key (kebab-case), add it to both `en` and
// `zh` blocks. Use `t("my.key")` in templates. Missing keys fall back to the
// English value (or the key itself if neither is defined).

import { computed } from "vue";
import { appLanguage } from "./state.js";

const messages = {
  en: {
    "nav.home": "Home",
    "nav.research_center": "BSH Research Center",
    "section.recent_reports": "Recent Reports",
    "section.news": "News",
    "section.external_research": "External Research",
    "section.hormuz_research": "Hormuz Research",
    "empty.no_reports": "No reports yet.",
    "empty.no_news": "Submit a link from the home page.",
    "empty.no_external_research": "Upload research from the home page.",
    "empty.no_hormuz": "No internal notes yet.",
    "status.done": "Done",
    "lang.toggle_to_zh": "中文",
    "lang.toggle_to_en": "English",
    "lang.app_language": "App language",
    "company.refresh": "Refresh data",
    "company.refreshing": "Refreshing…",
    "company.research_label": "Research",
    "company.insights": "Insights",
    "company.products": "Products",
    "company.competitors": "Competitors",
    "company.contracts": "Notable contracts",
    "company.acquisitions": "Acquisitions",
    "company.recent_news": "Recent news",
    "company.expand_all": "Expand all",
    "company.collapse_all": "Collapse all",
    "company.last_round": "Last round:",
    "company.total_raised": "Total raised:",
    "company.last_earnings": "Last earnings:",
    "company.translation_pending": "Translation pending…",
    "company.translation_unavailable": "Translation not available.",
    "common.loading": "Loading…",
  },
  zh: {
    "nav.home": "首页",
    "nav.research_center": "BSH 研究中心",
    "section.recent_reports": "近期报告",
    "section.news": "新闻",
    "section.external_research": "外部研究",
    "section.hormuz_research": "霍尔木兹研究",
    "empty.no_reports": "暂无报告。",
    "empty.no_news": "请从首页提交链接。",
    "empty.no_external_research": "请从首页上传研究。",
    "empty.no_hormuz": "暂无内部笔记。",
    "status.done": "完成",
    "lang.toggle_to_zh": "中文",
    "lang.toggle_to_en": "English",
    "lang.app_language": "界面语言",
    "company.refresh": "刷新数据",
    "company.refreshing": "刷新中…",
    "company.research_label": "研究",
    "company.insights": "洞察",
    "company.products": "产品",
    "company.competitors": "竞争对手",
    "company.contracts": "重要合同",
    "company.acquisitions": "收购",
    "company.recent_news": "近期新闻",
    "company.expand_all": "全部展开",
    "company.collapse_all": "全部折叠",
    "company.last_round": "最近一轮:",
    "company.total_raised": "总融资额:",
    "company.last_earnings": "最近财报:",
    "company.translation_pending": "翻译生成中…",
    "company.translation_unavailable": "暂无翻译。",
    "common.loading": "加载中…",
  },
};

export function t(key) {
  const lang = appLanguage.value;
  return (messages[lang] && messages[lang][key]) || messages.en[key] || key;
}

// Reactive computed wrapper so templates re-render when appLanguage changes.
// Use as: const tr = useT(); then tr("my.key") in template/computed.
export function useT() {
  return (key) => {
    // Touch the ref so the computed/template tracks it.
    void appLanguage.value;
    return t(key);
  };
}

export const currentLanguage = computed(() => appLanguage.value);
