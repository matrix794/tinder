import { useState } from "react";
import { useParams, Link } from "react-router";
import { ArrowLeft, Send, Paperclip, Smile, MoreVertical, Calendar, BookOpen } from "lucide-react";
import { motion } from "motion/react";
import { ImageWithFallback } from "./figma/ImageWithFallback";

interface Message {
  id: number;
  text: string;
  sender: "me" | "them";
  timestamp: string;
}

const mockMessages: Message[] = [
  {
    id: 1,
    text: "Привет! Я видела, что ты тоже изучаешь высшую математику 👋",
    sender: "them",
    timestamp: "10:30",
  },
  {
    id: 2,
    text: "Привет! Да, готовлюсь к экзамену. А ты на каком курсе?",
    sender: "me",
    timestamp: "10:32",
  },
  {
    id: 3,
    text: "На втором. У меня через две недели экзамен, хочу подготовиться как следует",
    sender: "them",
    timestamp: "10:33",
  },
  {
    id: 4,
    text: "Отлично! Может позанимаемся вместе? Я обычно в библиотеке МГУ по утрам",
    sender: "them",
    timestamp: "10:34",
  },
  {
    id: 5,
    text: "Звучит здорово! Могу завтра в 10:00, подойдёт?",
    sender: "me",
    timestamp: "10:36",
  },
];

const matchInfo = {
  name: "Анна Смирнова",
  university: "МГУ",
  image: "https://images.unsplash.com/photo-1758525866582-5c74fb7d9378?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHx5b3VuZyUyMHdvbWFuJTIwc3R1ZHlpbmclMjBib29rc3xlbnwxfHx8fDE3NzI4NzEzNjN8MA&ixlib=rb-4.1.0&q=80&w=1080",
  subjects: ["Высшая математика", "Программирование", "Физика"],
};

export function Chat() {
  const { matchId } = useParams();
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState(mockMessages);

  const handleSend = () => {
    if (message.trim()) {
      const newMessage: Message = {
        id: messages.length + 1,
        text: message,
        sender: "me",
        timestamp: new Date().toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      setMessages([...messages, newMessage]);
      setMessage("");
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border/50 backdrop-blur-xl bg-background/80">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link
                to="/matches"
                className="p-2 hover:bg-muted/50 rounded-full transition-colors"
              >
                <ArrowLeft className="h-5 w-5" />
              </Link>

              <div className="flex items-center gap-3">
                <div className="relative">
                  <div className="w-12 h-12 rounded-full overflow-hidden ring-2 ring-primary/20">
                    <ImageWithFallback
                      src={matchInfo.image}
                      alt={matchInfo.name}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-background" />
                </div>

                <div>
                  <h2 className="font-bold">{matchInfo.name}</h2>
                  <p className="text-sm text-muted-foreground">
                    {matchInfo.university}
                  </p>
                </div>
              </div>
            </div>

            <button className="p-2 hover:bg-muted/50 rounded-full transition-colors">
              <MoreVertical className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Subjects Info */}
      <div className="flex-shrink-0 border-b border-border/50 bg-primary/5">
        <div className="max-w-4xl mx-auto px-4 py-3">
          <div className="flex items-center gap-2 flex-wrap">
            <BookOpen className="h-4 w-4 text-primary" />
            <span className="text-sm text-muted-foreground">Общие предметы:</span>
            {matchInfo.subjects.map((subject, index) => (
              <span
                key={index}
                className="px-2 py-1 bg-primary/10 border border-primary/20 rounded-full text-xs text-primary"
              >
                {subject}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 py-6 space-y-4">
          {/* Match notification */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center mb-8"
          >
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary/10 border border-primary/20 rounded-full text-sm text-primary mb-2">
              <Calendar className="h-4 w-4" />
              <span>Вы совпали 2 часа назад</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Начните беседу и договоритесь о совместных занятиях
            </p>
          </motion.div>

          {/* Messages list */}
          {messages.map((msg, index) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              className={`flex ${msg.sender === "me" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[75%] ${
                  msg.sender === "me"
                    ? "bg-gradient-to-r from-primary to-secondary text-white"
                    : "bg-card backdrop-blur-xl border border-border"
                } rounded-2xl px-4 py-3 ${
                  msg.sender === "me" ? "rounded-br-md" : "rounded-bl-md"
                }`}
              >
                <p className="text-sm leading-relaxed">{msg.text}</p>
                <p
                  className={`text-xs mt-1 ${
                    msg.sender === "me" ? "text-white/70" : "text-muted-foreground"
                  }`}
                >
                  {msg.timestamp}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-border/50 backdrop-blur-xl bg-background/80 pb-safe">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-end gap-3">
            <button className="p-3 hover:bg-muted/50 rounded-full transition-colors flex-shrink-0">
              <Paperclip className="h-5 w-5 text-muted-foreground" />
            </button>

            <div className="flex-1 relative">
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Напишите сообщение..."
                rows={1}
                className="w-full px-4 py-3 pr-12 bg-card backdrop-blur-xl border border-border rounded-2xl resize-none focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all"
                style={{
                  minHeight: "48px",
                  maxHeight: "120px",
                }}
              />
              <button className="absolute right-3 bottom-3 p-1 hover:bg-muted/50 rounded-full transition-colors">
                <Smile className="h-5 w-5 text-muted-foreground" />
              </button>
            </div>

            <button
              onClick={handleSend}
              disabled={!message.trim()}
              className="p-3 bg-gradient-to-r from-primary to-secondary text-white rounded-full hover:shadow-lg hover:shadow-primary/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              <Send className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
