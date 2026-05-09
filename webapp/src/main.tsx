import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { bootTelegramWebApp } from "./lib/telegram";

const root = ReactDOM.createRoot(document.getElementById("root")!);

function Mount() {
  const [, setRev] = React.useState(0);
  React.useEffect(() => {
    bootTelegramWebApp(() => setRev((n) => n + 1));
  }, []);
  return <App />;
}

root.render(
  <React.StrictMode>
    <Mount />
  </React.StrictMode>,
);
