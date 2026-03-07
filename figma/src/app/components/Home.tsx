import { Link } from "react-router";
import { Heart, Users, MessageCircle, Award } from "lucide-react";
import { motion } from "motion/react";
import { ImageWithFallback } from "./figma/ImageWithFallback";
import heroImage from "figma:asset/67fe8e38a2df522422ff41bc28c7a69c80b2484c.png";

export function Home() {
  const features = [
    {
      icon: Heart,
      title: "Умный подбор",
      description: "Находим студентов с похожими предметами и целями",
    },
    {
      icon: Users,
      title: "Мэтчи",
      description: "Взаимные лайки — начинайте учиться вместе",
    },
    {
      icon: MessageCircle,
      title: "Чат",
      description: "Общайтесь и договаривайтесь о совместных занятиях",
    },
  ];

  return (
    <div className="min-h-screen pb-20 md:pb-0">
      {/* Hero Section */}
      <section className="relative overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-secondary/10 to-accent/10" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(59,130,246,0.1),transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_50%,rgba(139,92,246,0.1),transparent_50%)]" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-32">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
                <Award className="h-4 w-4 text-primary" />
                <span className="text-sm text-primary">Платформа №1 для студентов</span>
              </div>

              <h1 className="text-4xl md:text-6xl font-bold mb-6 leading-tight">
                Найди{" "}
                <span className="bg-gradient-to-r from-primary via-secondary to-accent bg-clip-text text-transparent">
                  партнёра
                </span>
                <br />
                для учёбы
              </h1>

              <p className="text-lg md:text-xl text-muted-foreground mb-8 leading-relaxed">
                Свайпай карточки студентов, находи тех, кто изучает те же предметы,
                и договаривайся о совместных занятиях. Учиться вместе — эффективнее!
              </p>

              <div className="flex flex-col sm:flex-row gap-4">
                <Link
                  to="/discover"
                  className="px-8 py-4 bg-gradient-to-r from-primary to-secondary rounded-full text-white font-semibold text-lg hover:shadow-2xl hover:shadow-primary/50 transition-all transform hover:scale-105 text-center"
                >
                  Начать поиск
                </Link>
                <Link
                  to="/auth"
                  className="px-8 py-4 bg-card backdrop-blur-xl border border-border rounded-full font-semibold text-lg hover:bg-muted/50 transition-all text-center"
                >
                  Узнать больше
                </Link>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="relative hidden md:block"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-primary via-secondary to-accent rounded-3xl blur-3xl opacity-20" />
              <ImageWithFallback
                src={heroImage}
                alt="Students studying together"
                className="relative rounded-3xl shadow-2xl w-full object-cover aspect-square"
              />
            </motion.div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="relative py-20 md:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-16"
          >
            <h2 className="text-3xl md:text-5xl font-bold mb-4">
              Как это работает
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Простой и эффективный способ найти партнёра для учёбы
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-8">
            {features.map((feature, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                className="group"
              >
                <div className="relative p-8 rounded-2xl bg-card backdrop-blur-xl border border-border hover:border-primary/50 transition-all hover:shadow-xl hover:shadow-primary/10">
                  <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-secondary/5 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity" />
                  
                  <div className="relative">
                    <div className="inline-flex p-4 rounded-2xl bg-gradient-to-br from-primary/10 to-secondary/10 mb-6">
                      <feature.icon className="h-8 w-8 text-primary" />
                    </div>
                    
                    <h3 className="text-xl font-bold mb-3">{feature.title}</h3>
                    <p className="text-muted-foreground leading-relaxed">
                      {feature.description}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-20 md:py-32">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="relative overflow-hidden rounded-3xl p-12 md:p-16 text-center"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-primary via-secondary to-accent" />
            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PHBhdHRlcm4gaWQ9ImdyaWQiIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHBhdGggZD0iTSAxMCAwIEwgMCAwIDAgMTAiIGZpbGw9Im5vbmUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS1vcGFjaXR5PSIwLjEiIHN0cm9rZS13aWR0aD0iMSIvPjwvcGF0dGVybj48L2RlZnM+PHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0idXJsKCNncmlkKSIvPjwvc3ZnPg==')] opacity-20" />
            
            <div className="relative">
              <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
                Готов найти партнёра для учёбы?
              </h2>
              <p className="text-xl text-white/90 mb-8 max-w-2xl mx-auto">
                Присоединяйся к тысячам студентов, которые уже учатся эффективнее вместе
              </p>
              <Link
                to="/auth"
                className="inline-block px-10 py-4 bg-white text-primary rounded-full font-semibold text-lg hover:shadow-2xl transition-all transform hover:scale-105"
              >
                Создать профиль
              </Link>
            </div>
          </motion.div>
        </div>
      </section>
    </div>
  );
}