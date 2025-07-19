"use client";

import React, { useEffect, useState, useRef, type ReactNode } from "react";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type ThreadMessageLike,
  type AppendMessage,
  type TextContentPart,
} from "@assistant-ui/react";
import { useChatStore } from "~/lib/store";
import { useNavigate } from "react-router";

async function fetchCrews() {
  try {
    const response = await fetch('/api/crews');
    const data = await response.json();
    
    if (data.status === "success" && Array.isArray(data.crews)) {
      // Update the store with available crews
      useChatStore.getState().setCrews(data.crews);
    } else {
      console.error("Failed to fetch crews", data);
    }
  } catch (error) {
    console.error("Error fetching crews", error);
  }
}

const convertMessage = (message: ThreadMessageLike) => {
  const textContent = message.content[0] as TextContentPart;
  if (!textContent || textContent.type !== "text") {
    throw new Error("Only text messages are supported");
  }
  
  return {
    role: message.role,
    content: textContent.text,
    timestamp: Date.now(),
  };
};

export function CrewAIChatUIRuntimeProvider({
  children,
  selectedCrewId,
}: Readonly<{
  children: ReactNode;
  selectedCrewId: string | null;
}>) {
  const navigate = useNavigate();
  const [isRunning, setIsRunning] = useState(false);
  const currentChatId = useChatStore((state) => state.currentChatId);
  const currentCrewId = useChatStore((state) => state.currentCrewId);
  const chatHistory = useChatStore((state) => state.chatHistory);
  const messages = useChatStore((state) => 
    currentChatId ? state.chatHistory[currentChatId]?.messages || [] : []
  );
  
  const onNew = async (message: AppendMessage) => {
    if (!currentChatId || !currentCrewId) return;
    const textContent = message.content[0] as TextContentPart;
    if (!textContent || textContent.type !== "text") {
      throw new Error("Only text messages are supported");
    }

    const userContent = textContent.text;
    const { addMessage, updateChatTitle, chatHistory } = useChatStore.getState();
    
    addMessage(currentChatId, {
      role: 'user',
      content: userContent,
      timestamp: Date.now(),
    });

    const chat = chatHistory[currentChatId]

    if (!chat.title || chat.title === "New Chat") {
      const updatedTitle = userContent.split(" ")[0];
      updateChatTitle(currentChatId, updatedTitle);
    }

    setIsRunning(true);
    
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: userContent,
          chat_id: currentChatId,
          crew_id: currentCrewId,
        }),
      });

      if (!response.ok) {
        throw new Error(`API request failed with status ${response.status}`);
      }

      const data = await response.json();
      
      if (data.status === "success" && data.content) {
        addMessage(currentChatId, {
          role: 'assistant',
          content: data.content,
          timestamp: Date.now(),
        });
      } else {
        throw new Error(data.message || "Unknown error occurred");
      }
    } catch (error) {
      console.error("Error in chat:", error);
    } finally {
      setIsRunning(false);
    }
  };

  const runtime = useExternalStoreRuntime({
    isRunning,
    messages: messages.map(msg => ({
      role: msg.role,
      content: [{ type: "text" as const, text: msg.content }],
    })),
    convertMessage,
    onNew,
  });
  
  async function initializeChat() {
    setIsRunning(true);

    try {
      await fetchCrews();
      
      const { addMessage, createChat, setCurrentChat, findChatByCrewId, generateUUID } = useChatStore.getState();
      
      // Check if we have a stored chat ID in localStorage
      const storedChatId = localStorage.getItem('crewai_chat_id');
      const storedCrewId = localStorage.getItem('crewai_crew_id');
      
      // Prioritize selectedCrewId from URL params over localStorage
      const effectiveCrewId = selectedCrewId || storedCrewId;
      
      // Determine which chat ID to use
      let chatId;
      
      // If we have a stored chat ID and it exists in our chat history
      if (storedChatId && chatHistory[storedChatId]) {
        chatId = storedChatId;
        setCurrentChat(chatId);
        
        // Update URL if needed
        if (window.location.pathname.includes('/chat/')) {
          navigate(`/chat/${chatId}?crew=${effectiveCrewId || ''}`);
        }
        
        // Initialize crew context for existing chat if we have a crew ID
        if (effectiveCrewId) {
          // Check if initialization is needed to prevent double calls
          if (!shouldInitialize(chatId, effectiveCrewId)) {
            return;
          }
          
          console.log('Initializing existing chat with crew:', { chatId, crewId: effectiveCrewId });
          try {
            const response = await fetch(`/api/initialize`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                chat_id: chatId,
                crew_id: effectiveCrewId,
              }),
            });
            
            const data = await response.json();
            
            if (data.status === "success") {
              console.log('Successfully initialized existing chat with crew');
              if (data.message) {
                addMessage(chatId, {
                  role: 'assistant',
                  content: data.message,
                  timestamp: Date.now(),
                });
              }
            } else {
              console.error("Failed to initialize existing chat with crew", data);
            }
          } catch (error) {
            console.error("Error initializing existing chat with crew", error);
          }
        }
      } else {
        // Otherwise use current chat ID or generate a new one
        chatId = currentChatId || generateUUID();
        
        // Check if we already have a chat for this crew
        if (effectiveCrewId) {
          const existingChatId = findChatByCrewId(effectiveCrewId);
          if (existingChatId) {
            chatId = existingChatId;
          } else {
            createChat(chatId, effectiveCrewId);
          }
        } else {
          createChat(chatId, null);
        }
        
        setCurrentChat(chatId);
        
        // Store the new chat ID and effective crew ID
        localStorage.setItem('crewai_chat_id', chatId);
        if (effectiveCrewId) {
          localStorage.setItem('crewai_crew_id', effectiveCrewId);
        }
        
        // Only initialize with API if it's a new chat
        const response = await fetch(`/api/initialize`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            chat_id: chatId,
            crew_id: effectiveCrewId,
          }),
        });
        
        const data = await response.json();
        
        if (data.status === "success") {
          if (data.message) {
            addMessage(chatId, {
              role: 'assistant',
              content: data.message,
              timestamp: Date.now(),
            });
          }
        } else {
          console.error("Failed to initialize chat", data);
        }
      }
    } catch (error) {
      console.error("Error initializing chat", error);
    } finally {
      setIsRunning(false);
    }
  }

  useEffect(() => {
    if (typeof window !== 'undefined') {
      initializeChat();
    }
  }, []);
  
  // Effect to update localStorage when current chat or crew changes
  useEffect(() => {
    if (currentChatId) {
      localStorage.setItem('crewai_chat_id', currentChatId);
    }
    
    if (selectedCrewId) {
      localStorage.setItem('crewai_crew_id', selectedCrewId);
    } else if (currentCrewId) {
      localStorage.setItem('crewai_crew_id', currentCrewId);
    }
  }, [currentChatId, currentCrewId, selectedCrewId]);
  
  // Ref to track previous crew ID to detect changes
  const prevCrewIdRef = useRef<string | null>(null);
  
  // Ref to track initialization state to prevent double initialization
  const initializationStateRef = useRef<Set<string>>(new Set());
  
  // Helper function to create unique initialization key
  const getInitializationKey = (chatId: string, crewId: string) => `${chatId}-${crewId}`;
  
  // Helper function to check if initialization is needed
  const shouldInitialize = (chatId: string, crewId: string) => {
    const key = getInitializationKey(chatId, crewId);
    if (initializationStateRef.current.has(key)) {
      console.log('Skipping initialization - already completed for:', { chatId, crewId });
      return false;
    }
    initializationStateRef.current.add(key);
    return true;
  };
  
  // Effect to handle crew changes and initialize appropriate chat
  useEffect(() => {
    console.log('Crew change effect triggered:', { 
      currentChatId, 
      selectedCrewId, 
      storeCrewId: currentCrewId, 
      prevCrewId: prevCrewIdRef.current 
    });
    
    // Skip if we don't have a selected crew ID
    if (!selectedCrewId) {
      console.log('Skipping crew change - missing crew ID');
      return;
    }
    
    // Always proceed if this is the first time (prevCrewIdRef.current is null)
    // or if the crew ID has actually changed
    const isFirstTime = prevCrewIdRef.current === null;
    const hasCrewChanged = prevCrewIdRef.current !== selectedCrewId;
    
    if (!isFirstTime && !hasCrewChanged) {
      console.log('Skipping crew change - crew ID unchanged and not first time');
      return;
    }
    
    console.log('Crew changed from', prevCrewIdRef.current, 'to', selectedCrewId);
    
    // Update the ref
    prevCrewIdRef.current = selectedCrewId;
    
    const handleCrewChange = async () => {
      console.log('Handling crew change to:', selectedCrewId);
      setIsRunning(true);
      
      try {
        const { 
          findChatByCrewId, 
          generateUUID, 
          createChat, 
          setCurrentChat, 
          setCurrentCrew,
          addMessage,
          updateChatThread,
          chatHistory
        } = useChatStore.getState();
        
        // Find the crew name
        const crews = useChatStore.getState().crews;
        const crew = crews.find(c => c.id === selectedCrewId);
        const crewName = crew?.name || 'Unknown Crew';
        
        // Step 1: Check if we already have an existing chat for this crew
        const existingChatId = findChatByCrewId(selectedCrewId);
        let chatId;
        
        if (existingChatId) {
          console.log('Found existing chat for crew:', existingChatId);
          chatId = existingChatId;
          
          // Use the existing chat
          setCurrentChat(chatId);
          setCurrentCrew(selectedCrewId);
          
          // Update URL if needed
          if (window.location.pathname.includes('/chat/')) {
            navigate(`/chat/${chatId}?crew=${selectedCrewId}`);
          }
          
          // Check if initialization is needed to prevent double calls
          if (!shouldInitialize(chatId, selectedCrewId)) {
            return;
          }
          
          // Call the API to initialize crew context for the existing chat
          const payload = {
            chat_id: chatId,
            crew_id: selectedCrewId,
          };
          console.log('Calling /api/initialize for existing chat with payload:', payload);
          
          try {
            const response = await fetch(`/api/initialize`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify(payload),
            });
            
            const data = await response.json();
            
            if (data.status === "success") {
              console.log('Successfully initialized existing chat with crew');
              // Update the chat thread with the crew info
              updateChatThread(chatId, {
                crewId: selectedCrewId,
                crewName: crewName,
              });
              
              // Add welcome message from the assistant if provided
              if (data.message) {
                addMessage(chatId, {
                  role: 'assistant',
                  content: data.message,
                  timestamp: Date.now(),
                });
              }
            } else {
              console.error("Failed to initialize existing chat with crew", data);
              // Add fallback system message
              addMessage(chatId, {
                role: 'system',
                content: `Switched to existing chat with ${crewName}.`,
                timestamp: Date.now(),
              });
            }
          } catch (error) {
            console.error("Error initializing existing chat with crew", error);
            // Add fallback system message
            addMessage(chatId, {
              role: 'system',
              content: `Switched to existing chat with ${crewName}.`,
              timestamp: Date.now(),
            });
          }
        } else {
          console.log('Creating new chat for crew:', selectedCrewId);
          // Create a new chat for this crew
          chatId = generateUUID();
          createChat(chatId, selectedCrewId);
          setCurrentChat(chatId);
          setCurrentCrew(selectedCrewId);
          
          // Update URL if needed
          if (window.location.pathname.includes('/chat/')) {
            navigate(`/chat/${chatId}?crew=${selectedCrewId}`);
          }
          
          // Store the new chat ID
          localStorage.setItem('crewai_chat_id', chatId);
          localStorage.setItem('crewai_crew_id', selectedCrewId);
          
          // Mark initialization as in progress for new chat
          initializationStateRef.current.add(getInitializationKey(chatId, selectedCrewId));
          
          // Call the API to initialize with the new crew
          const payload = {
            chat_id: chatId,
            crew_id: selectedCrewId,
          };
          console.log('Calling /api/initialize with payload:', payload);
          
          const response = await fetch(`/api/initialize`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
          });
          
          const data = await response.json();
          
          if (data.status === "success") {
            // Update the chat thread with the new crew info
            updateChatThread(chatId, {
              crewId: selectedCrewId,
              crewName: crewName,
            });
            
            // Add welcome message from the assistant if provided
            if (data.message) {
              addMessage(chatId, {
                role: 'assistant',
                content: data.message,
                timestamp: Date.now(),
              });
            }
          } else {
            console.error("Failed to initialize chat with new crew", data);
          }
        }
      } catch (error) {
        console.error("Error handling crew change", error);
      } finally {
        setIsRunning(false);
      }
    };
    
    // Handle the crew change
    handleCrewChange();
    
  }, [selectedCrewId, navigate]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}