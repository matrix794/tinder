import { Outlet, Link, useLocation } from "react-router";
import { GraduationCap, Sparkles, Users, MessageCircle } from "lucide-react";
import { useEffect } from "react";

export function Layout() {
  const location = useLocation();

  useEffect(() => {
    // Apply dark mode
    document.documentElement.classList.add('dark');
  }, []);

  const navItems = [
    { path: "/discover", icon: Sparkles, label: "Открыть" },
    { path: "/matches", icon: Users, label: "Мэтчи" },
  ];

  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 backdrop-blur-xl bg-background/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-2 group">
              <div className="relative">
                <div className="absolute inset-0 bg-gradient-to-r from-primary via-secondary to-accent blur-lg opacity-50 group-hover:opacity-75 transition-opacity" />
                <GraduationCap className="h-8 w-8 text-primary relative" />
              </div>
              <span className="text-xl font-bold bg-gradient-to-r from-primary via-secondary to-accent bg-clip-text text-transparent">
                StudyTinder
              </span>
            </Link>

            <nav className="hidden md:flex items-center gap-6">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
                    isActive(item.path)
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>

            <Link
              to="/auth"
              className="px-6 py-2 bg-gradient-to-r from-primary to-secondary rounded-full text-white font-medium hover:shadow-lg hover:shadow-primary/50 transition-all"
            >
              Войти
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="pt-16">
        <Outlet />
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border/50 backdrop-blur-xl bg-background/80">
        <div className="grid grid-cols-3 gap-1 px-4 py-3">
          <Link
            to="/discover"
            className={`flex flex-col items-center gap-1 py-2 rounded-lg transition-all ${
              isActive("/discover")
                ? "text-primary"
                : "text-muted-foreground"
            }`}
          >
            <Sparkles className="h-6 w-6" />
            <span className="text-xs">Открыть</span>
          </Link>
          <Link
            to="/matches"
            className={`flex flex-col items-center gap-1 py-2 rounded-lg transition-all ${
              isActive("/matches")
                ? "text-primary"
                : "text-muted-foreground"
            }`}
          >
            <Users className="h-6 w-6" />
            <span className="text-xs">Мэтчи</span>
          </Link>
          <Link
            to="/"
            className={`flex flex-col items-center gap-1 py-2 rounded-lg transition-all ${
              isActive("/")
                ? "text-primary"
                : "text-muted-foreground"
            }`}
          >
            <GraduationCap className="h-6 w-6" />
            <span className="text-xs">Главная</span>
          </Link>
        </div>
      </nav>
    </div>
  );
}