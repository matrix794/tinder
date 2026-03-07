import { createBrowserRouter } from "react-router";
import { Layout } from "./components/Layout";
import { Home } from "./components/Home";
import { Discover } from "./components/Discover";
import { Matches } from "./components/Matches";
import { Chat } from "./components/Chat";
import { Auth } from "./components/Auth";
import { ProfileSetup } from "./components/ProfileSetup";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Home },
      { path: "discover", Component: Discover },
      { path: "matches", Component: Matches },
      { path: "chat/:matchId", Component: Chat },
      { path: "profile-setup", Component: ProfileSetup },
    ],
  },
  {
    path: "/auth",
    Component: Auth,
  },
]);
