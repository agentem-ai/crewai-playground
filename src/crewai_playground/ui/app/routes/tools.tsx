import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import { Label } from "~/components/ui/label";
import { Layout } from "../components/Layout";
import { Alert } from "~/components/ui/alert";

interface Tool {
  name: string;
  description: string;
  parameters: {
    type: string;
    properties: Record<
      string,
      {
        type: string;
        description: string;
      }
    >;
    required?: string[];
  };
}

export function meta() {
  return [
    { title: "CrewAI - Tools Testing" },
    { name: "description", content: "Test your CrewAI tools" },
  ];
}

export default function Tools() {
  const [loading, setLoading] = useState(true);
  const [tools, setTools] = useState<Tool[]>([]);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<string>("");
  const [error, setError] = useState<string>("");

  // Fetch available tools on component mount
  useEffect(() => {
    const fetchTools = async () => {
      try {
        setLoading(true);
        const response = await fetch("/api/tools");
        const data = await response.json();

        if (data.status === "success" && Array.isArray(data.tools)) {
          setTools(data.tools);
          if (data.tools.length > 0) {
            setSelectedTool(data.tools[0]);
            // Initialize input values for the first tool
            initializeInputValues(data.tools[0]);
          }
        } else {
          setError(
            "Failed to load tools: " + (data.message || "Unknown error")
          );
        }
      } catch (error) {
        console.error("Error fetching tools:", error);
        setError(
          "Failed to load tools. Please check if the server is running."
        );
      } finally {
        setLoading(false);
      }
    };

    fetchTools();
  }, []);

  const initializeInputValues = (tool: Tool) => {
    if (!tool || !tool.parameters || !tool.parameters.properties) {
      setInputValues({});
      return;
    }

    const initialValues: Record<string, string> = {};
    Object.keys(tool.parameters.properties).forEach((key) => {
      initialValues[key] = "";
    });
    setInputValues(initialValues);
  };

  const handleToolSelect = (tool: Tool) => {
    setSelectedTool(tool);
    initializeInputValues(tool);
    setResult("");
    setError("");
  };

  const handleInputChange = (paramName: string, value: string) => {
    setInputValues((prev) => ({
      ...prev,
      [paramName]: value,
    }));
  };

  const handleSubmit = async () => {
    if (!selectedTool) return;

    try {
      setLoading(true);
      setError("");
      setResult("");

      const response = await fetch(`/api/tools/${selectedTool.name}/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ inputs: inputValues }),
      });

      const data = await response.json();

      if (data.status === "success") {
        setResult(
          typeof data.result === "object"
            ? JSON.stringify(data.result, null, 2)
            : String(data.result)
        );
      } else {
        setError(data.message || "An error occurred while executing the tool");
      }
    } catch (error) {
      console.error("Error executing tool:", error);
      setError("Failed to execute tool. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const rightSidebar = (
    <div className="space-y-2">
      <h2 className="text-lg font-semibold mb-2">Available Tools</h2>
      {loading && tools.length === 0 ? (
        <div className="flex justify-center p-4">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary"></div>
        </div>
      ) : tools.length > 0 ? (
        <div className="space-y-2">
          {tools.map((tool) => (
            <Button
              key={tool.name}
              variant={selectedTool?.name === tool.name ? "secondary" : "ghost"}
              className="w-full justify-start text-left"
              onClick={() => handleToolSelect(tool)}
            >
              {tool.name}
            </Button>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">No tools available</p>
      )}
    </div>
  );

  return (
    <Layout rightSidebar={rightSidebar}>
      <div className="p-6">
        {selectedTool ? (
          <div className="max-w-3xl mx-auto bg-card rounded-lg shadow-sm p-6 border">
            <h2 className="text-2xl font-bold mb-2">{selectedTool.name}</h2>
            <p className="text-muted-foreground mb-6">
              {selectedTool.description}
            </p>

            <div className="space-y-6 bg-muted/30 p-6 rounded-lg border">
              <h3 className="text-lg font-semibold">Parameters</h3>
              {selectedTool.parameters && selectedTool.parameters.properties ? (
                <div className="space-y-4">
                  {Object.entries(selectedTool.parameters.properties).map(
                    ([paramName, paramDetails]) => (
                      <div key={paramName} className="space-y-2">
                        <Label
                          htmlFor={paramName}
                          className="text-base font-medium"
                        >
                          {paramName}
                          {selectedTool.parameters.required?.includes(
                            paramName
                          ) && <span className="text-red-500 ml-1">*</span>}
                        </Label>
                        {paramDetails.type === "string" &&
                        paramDetails.description
                          .toLowerCase()
                          .includes("multi") ? (
                          <Textarea
                            id={paramName}
                            placeholder={paramDetails.description}
                            value={inputValues[paramName] || ""}
                            onChange={(e) =>
                              handleInputChange(paramName, e.target.value)
                            }
                            className="w-full"
                            rows={4}
                          />
                        ) : (
                          <Input
                            id={paramName}
                            type={
                              paramDetails.type === "number" ? "number" : "text"
                            }
                            placeholder={paramDetails.description}
                            value={inputValues[paramName] || ""}
                            onChange={(e) =>
                              handleInputChange(paramName, e.target.value)
                            }
                            className="w-full"
                          />
                        )}
                        <p className="text-xs text-muted-foreground">
                          {paramDetails.description}
                        </p>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <p className="text-muted-foreground">
                  This tool has no parameters
                </p>
              )}

              <div className="flex justify-center mt-8">
                <Button
                  onClick={handleSubmit}
                  disabled={loading}
                  className="px-8"
                >
                  {loading ? (
                    <>
                      <span className="animate-spin mr-2">⏳</span>
                      Processing...
                    </>
                  ) : (
                    "Execute Tool"
                  )}
                </Button>
              </div>

              {error && (
                <Alert variant="destructive" className="mt-4">
                  {error}
                </Alert>
              )}

              {result && (
                <div className="mt-8 bg-muted/50 p-6 rounded-lg border">
                  <h3 className="text-lg font-semibold mb-4">Result</h3>
                  <div className="bg-background p-4 rounded-md overflow-auto max-h-96 border">
                    <pre className="text-sm whitespace-pre-wrap">{result}</pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-64 max-w-3xl mx-auto bg-card rounded-lg shadow-sm p-6 border">
            <p className="text-muted-foreground text-lg">
              {loading ? "Loading tools..." : "Select a tool from the sidebar"}
            </p>
          </div>
        )}
      </div>
    </Layout>
  );
}
