import "@fontsource/hanken-grotesk/300.css";
import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/tokens.css";
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router";

import { Shell } from "./Shell";
import { DocumentPage } from "./pages/DocumentPage";
import { EmptyPage } from "./pages/EmptyPage";
import { IndexPage } from "./pages/IndexPage";

const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to="/index" replace /> },
      { path: "index", element: <IndexPage /> },
      { path: "documents/:documentId", element: <DocumentPage /> },
      {
        path: "map",
        element: (
          <EmptyPage
            label="MAP"
            title="The map arrives with entities and facts"
            body="Ownership, boards and audit links are drawn once facts are extracted from the filings. For now the graph holds the filings themselves."
          />
        ),
      },
      {
        path: "checks",
        element: (
          <EmptyPage
            label="CHECKS"
            title="Nothing to check yet"
            body="Extracted figures and new names wait here for a person to accept or correct them. Nothing has been extracted yet."
          />
        ),
      },
      {
        path: "kpis",
        element: (
          <EmptyPage
            label="KPIs"
            title="KPIs follow checked figures"
            body="Every KPI, the F-score and the Sharia rules will be documented here, computed only from figures a person has checked."
          />
        ),
      },
      {
        path: "*",
        element: <EmptyPage label="NOT FOUND" title="This page doesn't exist" body="The address doesn't match any page in the app." />,
      },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
