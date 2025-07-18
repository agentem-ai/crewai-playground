import { type ReactNode, useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router";
import { Moon, Plus, Sun, Trash2 } from "lucide-react";
import { Button } from "~/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { useChatStore } from "~/lib/store";
import { cn } from "~/lib/utils";
import { DeleteChatModal } from "./delete-chat-modal";

interface ChatSidebarProps {
  children?: ReactNode;
}

export const ChatSidebar = ({ children }: ChatSidebarProps) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [chatToDelete, setChatToDelete] = useState<string | null>(null);
  const {
    crews,
    currentCrewId,
    currentChatId,
    chatHistory,
    isDarkMode,
    setCrews,
    setCurrentCrew,
    setCurrentChat,
    createChat,
    deleteChat,
    toggleDarkMode,
    findChatByCrewId,
    generateUUID,
  } = useChatStore();

  // Generate a new chat ID
  const generateChatId = () => {
    return generateUUID();
  };

  // Set initial chat when component mounts
  useEffect(() => {
    // Fetch crews if not already loaded
    if (!crews || !Array.isArray(crews) || crews.length === 0) {
      fetch("/api/crews")
        .then((response) => response.json())
        .then((data) => {
          if (data.status === "success" && Array.isArray(data.crews)) {
            setCrews(data.crews);
          }
        })
        .catch((error) => console.error("Error fetching crews:", error));
    }

    // Check if we have a chat ID in the URL
    const chatIdFromUrl = searchParams.get("chatId");
    const crewIdFromUrl = searchParams.get("crew");

    // Check if we have a stored chat ID in localStorage
    const storedChatId = localStorage.getItem("crewai_chat_id");
    const storedCrewId = localStorage.getItem("crewai_crew_id");

    if (!chatIdFromUrl) {
      // No chat ID in URL, check localStorage and chat history
      if (storedChatId && chatHistory[storedChatId]) {
        // We have a stored chat ID that exists in history
        setCurrentChat(storedChatId);
        if (storedCrewId) {
          setCurrentCrew(storedCrewId);
        }

        // Update URL params
        setSearchParams((params) => {
          params.set("chatId", storedChatId);
          if (storedCrewId) {
            params.set("crew", storedCrewId);
          }
          return params;
        });
      } else if (Object.keys(chatHistory).length > 0) {
        // No stored chat ID or it doesn't exist, but we have chats in history
        // Use the most recent chat
        const sortedChats = Object.values(chatHistory).sort(
          (a, b) => b.lastUpdated - a.lastUpdated
        );
        const mostRecentChat = sortedChats[0];

        setCurrentChat(mostRecentChat.id);
        if (mostRecentChat.crewId) {
          setCurrentCrew(mostRecentChat.crewId);
        }

        // Update localStorage
        localStorage.setItem("crewai_chat_id", mostRecentChat.id);
        if (mostRecentChat.crewId) {
          localStorage.setItem("crewai_crew_id", mostRecentChat.crewId);
        }

        // Update URL params
        setSearchParams((params) => {
          params.set("chatId", mostRecentChat.id);
          if (mostRecentChat.crewId) {
            params.set("crew", mostRecentChat.crewId);
          }
          return params;
        });
      } else {
        // No chats in history, create a new one
        const newChatId = generateChatId();
        createChat(newChatId, currentCrewId);
        setCurrentChat(newChatId);

        // Update localStorage
        localStorage.setItem("crewai_chat_id", newChatId);
        if (currentCrewId) {
          localStorage.setItem("crewai_crew_id", currentCrewId);
        }

        // Update URL params
        setSearchParams((params) => {
          params.set("chatId", newChatId);
          if (currentCrewId) {
            params.set("crew", currentCrewId);
          }
          return params;
        });
      }
    } else if (chatHistory[chatIdFromUrl]) {
      // Chat ID from URL exists in history, use it
      setCurrentChat(chatIdFromUrl);

      // Update localStorage
      localStorage.setItem("crewai_chat_id", chatIdFromUrl);

      // Handle crew ID if present
      if (crewIdFromUrl) {
        setCurrentCrew(crewIdFromUrl);
        localStorage.setItem("crewai_crew_id", crewIdFromUrl);
      }
    }
  }, [
    chatHistory,
    currentCrewId,
    searchParams,
    setCurrentChat,
    setSearchParams,
    createChat,
    crews?.length || 0,
    setCrews,
    setCurrentCrew,
  ]);

  // Create a new chat
  const handleNewChat = () => {
    const chatId = generateChatId();
    const chatTitle = "New Chat"; // Set a default title or prompt for user input
    createChat(chatId, currentCrewId, chatTitle); // Pass the title to createChat
    setCurrentChat(chatId);
    setSearchParams((params) => {
      params.set("chatId", chatId);
      if (currentCrewId) {
        params.set("crew", currentCrewId);
      }
      return params;
    });
  };

  // Handle crew selection
  const handleCrewChange = (crewId: string) => {
    setCurrentCrew(crewId);
    
    // Check if there's an existing chat for this crew
    const existingChatId = findChatByCrewId(crewId);
    
    if (existingChatId) {
      // Open the existing chat for this crew
      setCurrentChat(existingChatId);
      
      // Update localStorage
      localStorage.setItem("crewai_chat_id", existingChatId);
      localStorage.setItem("crewai_crew_id", crewId);
      
      // Update URL params
      setSearchParams((params) => {
        params.set("chatId", existingChatId);
        params.set("crew", crewId);
        return params;
      });
    } else {
      // No existing chat for this crew, create a new one
      const newChatId = generateChatId();
      createChat(newChatId, crewId, "New Chat");
      setCurrentChat(newChatId);
      
      // Update localStorage
      localStorage.setItem("crewai_chat_id", newChatId);
      localStorage.setItem("crewai_crew_id", crewId);
      
      // Update URL params
      setSearchParams((params) => {
        params.set("chatId", newChatId);
        params.set("crew", crewId);
        return params;
      });
    }
  };

  // Handle chat selection
  const handleChatSelect = (chatId: string) => {
    const chat = chatHistory[chatId];
    if (!chat) return;

    // Update localStorage with selected chat
    localStorage.setItem("crewai_chat_id", chatId);
    if (chat.crewId) {
      localStorage.setItem("crewai_crew_id", chat.crewId);
    }

    // Navigate to the chat URL to trigger proper crew initialization
    // This will cause the CrewAIChatUIRuntimeProvider to handle crew changes properly
    const chatUrl = `/chat?chatId=${chatId}${chat.crewId ? `&crew=${chat.crewId}` : ''}`;
    navigate(chatUrl);
  };

  // Handle chat deletion
  const handleDeleteChat = (chatId: string) => {
    setChatToDelete(chatId);
  };

  const confirmDelete = () => {
    if (chatToDelete) {
      deleteChat(chatToDelete);
      if (currentChatId === chatToDelete) {
        setCurrentChat(null);
        setSearchParams((params) => {
          params.delete("chatId");
          return params;
        });
      }
      setChatToDelete(null);
    }
  };

  // Sort chats by last updated
  const sortedChats = chatHistory ? Object.values(chatHistory).sort(
    (a, b) => b.lastUpdated - a.lastUpdated
  ) : [];

  // Early return if essential data is not available
  if (!chatHistory) {
    return (
      <aside className="flex h-full flex-col">
        <div className="space-y-6">
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Loading...</h3>
          </div>
        </div>
      </aside>
    );
  }

  return (
    <>
      <aside className="flex h-full flex-col">
        <div className="space-y-6">
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Select a Crew</h3>
            <Select
              value={currentCrewId ?? ""}
              onValueChange={handleCrewChange}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a crew">
                  {(crews && Array.isArray(crews) ? crews.find((c) => c.id === currentCrewId)?.name : null) ||
                    "Select a crew"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {crews && Array.isArray(crews) && crews.map((crew) => (
                  <SelectItem key={crew.id} value={crew.id}>
                    {crew.name || 'Unnamed Crew'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button onClick={handleNewChat} className="w-full">
            <Plus className="mr-2 h-4 w-4" />
            New Chat
          </Button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto pt-6">
          <h3 className="text-lg font-semibold">Chats</h3>
          {sortedChats && Array.isArray(sortedChats) && sortedChats.map((chat) => {
            if (!chat || !chat.id) return null;
            return (
              <div
                key={chat.id}
                className={cn(
                  "group flex items-center justify-between rounded-lg px-3 py-2 hover:bg-accent/50 cursor-pointer",
                  currentChatId === chat.id && "bg-accent"
                )}
                onClick={() => handleChatSelect(chat.id)}
              >
              <div className="flex-1 truncate">
                <p className="truncate text-sm font-medium">{chat.title}</p>
                {chat.crewName && (
                  <p className="truncate text-xs text-muted-foreground">
                    {chat.crewName}
                  </p>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 opacity-0 group-hover:opacity-100"
                onClick={(e: React.MouseEvent) => {
                  e.stopPropagation();
                  handleDeleteChat(chat.id);
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            );
          })}
        </div>
      </aside>
      <DeleteChatModal
        isOpen={chatToDelete !== null}
        onClose={() => setChatToDelete(null)}
        onConfirm={confirmDelete}
      />
    </>
  );
};
