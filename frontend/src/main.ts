import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";
import "leaflet/dist/leaflet.css";

// 页面状态由根组件管理，不引入额外路由。
createApp(App).mount("#app");
