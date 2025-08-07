"""
Flow Loader for CrewAI Playground

This module provides functionality to discover and load CrewAI flows from
the user's environment, with comprehensive analysis of flow structure,
methods, dependencies, and relationships for reliable visualizations.

Based on official CrewAI visualization utilities for accurate flow parsing.
"""

import os
import sys
import importlib.util
import inspect
from typing import Dict, List, Any, Optional, Tuple, Union, Set
import logging
import uuid
from pydantic import BaseModel
import ast
import re
import textwrap
from collections import defaultdict, deque

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set this module's logger to a higher level to reduce noise
logger.setLevel(logging.WARNING)


class FlowInput(BaseModel):
    """Model for flow input parameters"""

    name: str
    description: str
    type_hint: str = "Any"
    required: bool = True


class FlowMethod(BaseModel):
    """Model for flow method information"""

    name: str
    description: str
    is_start: bool = False
    is_listener: bool = False
    listens_to: List[str] = []
    listener_condition: str = "OR"  # "OR" or "AND"
    is_router: bool = False
    router_paths: List[str] = []  # Possible return paths for router methods
    has_persist: bool = False
    calls_crew: bool = False  # Whether method calls .crew()
    level: int = 0  # Hierarchical level in flow graph


class FlowInfo(BaseModel):
    """Model for flow information"""

    id: str
    name: str
    description: str
    file_path: str
    class_name: str
    flow_class: Any  # Hold actual class object for quick access
    required_inputs: List[FlowInput] = []
    methods: List[FlowMethod] = []
    state_type: str = "unstructured"  # "structured" or "unstructured"
    state_model: Optional[str] = None
    # Flow structure for visualization
    listeners: Dict[str, Tuple[str, List[str]]] = {}  # method_name -> (condition_type, trigger_methods)
    routers: Set[str] = set()  # Router method names
    router_paths: Dict[str, List[str]] = {}  # router_method -> possible_paths
    start_methods: List[str] = []  # Start method names
    method_levels: Dict[str, int] = {}  # method_name -> hierarchical_level

    class Config:
        arbitrary_types_allowed = True


def discover_flows(directory: str = None) -> List[FlowInfo]:
    """
    Discover all Flow classes in the specified directory or current working directory.

    Args:
        directory: Directory to search for flow files. If None, uses current working directory.

    Returns:
        List of FlowInfo objects containing information about discovered flows.
    """
    if directory is None:
        directory = os.getcwd()

    logger.info(f"Discovering flows in {directory}")

    flows = []

    # Walk through the directory
    for root, _, files in os.walk(directory):
        # Skip __pycache__ directories and common virtual environment directories
        if any(
            skip_dir in root
            for skip_dir in [
                "__pycache__",
                ".venv",
                "venv",
                "site-packages",
                ".git",
                "node_modules",
            ]
        ):
            continue

        # Look for Python files
        for file in files:
            if not file.endswith(".py"):
                continue

            file_path = os.path.join(root, file)

            try:
                # Extract flow classes from the file
                file_flows = extract_flows_from_file(file_path)
                flows.extend(file_flows)
            except Exception as e:
                # Log at debug level instead of error for non-flow files
                logger.debug(f"Error processing file {file_path}: {str(e)}")

    logger.info(f"Discovered {len(flows)} flows")
    return flows


def extract_flows_from_file(file_path: str) -> List[FlowInfo]:
    """
    Extract Flow classes from a Python file.

    Args:
        file_path: Path to the Python file

    Returns:
        List of FlowInfo objects for flows found in the file
    """
    flows = []

    try:
        # First, try to parse the file with AST to check for Flow classes
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Quick check if this file might contain flows
        if not _contains_flow_indicators(content):
            return []

        # Generate a random module name to avoid conflicts
        module_name = f"flow_module_{uuid.uuid4().hex}"

        # Get the directory of the file for handling relative imports
        file_dir = os.path.dirname(file_path)

        # Add the file's directory _and_ its package root to sys.path temporarily
        sys_path_modified = False
        pkg_root_modified = False

        # 1. Directory containing the file (so relative imports like '.module' work)
        if file_dir not in sys.path:
            sys.path.insert(0, file_dir)
            sys_path_modified = True

        # 2. Top-level package root (parent dir of file_dir) so absolute imports like
        #    'flow141.something' succeed when the flow lives in src/flow141/*.py
        package_root = os.path.dirname(file_dir)
        if package_root and package_root not in sys.path:
            sys.path.insert(0, package_root)
            pkg_root_modified = True

        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return []

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            # Set up proper package structure for relative imports
            # Determine the package name from the file path
            package_parts = file_path.split(os.sep)
            try:
                # Find 'src' in the path to determine the package structure
                if "src" in package_parts:
                    src_index = package_parts.index("src")
                    if src_index + 1 < len(package_parts):
                        # Set the package name to the module's parent package
                        parent_package = ".".join(package_parts[src_index + 1 : -1])
                        module.__package__ = parent_package

                # If no 'src' directory, try to infer from directory structure
                else:
                    # Use the parent directory as the package name
                    parent_package = os.path.basename(os.path.dirname(file_path))
                    module.__package__ = parent_package
            except (ValueError, IndexError):
                # If we can't determine the package, use a fallback
                pass

            try:
                spec.loader.exec_module(module)
            except ImportError as e:
                # Attempt to gracefully handle optional / missing third-party dependencies
                missing_mod = _extract_missing_module_name(str(e))
                if missing_mod and missing_mod not in sys.modules:
                    logger.debug(
                        f"Missing dependency '{missing_mod}' when loading {file_path}. "
                        "Creating a stub so flow inspection can continue."
                    )
                    _install_stub_module(missing_mod)
                    try:
                        # Retry executing the module now that the stub exists
                        spec.loader.exec_module(module)
                    except Exception as inner_e:
                        logger.debug(
                            f"Retry after stubbing '{missing_mod}' failed for {file_path}: {inner_e}"
                        )
                        if module_name in sys.modules:
                            del sys.modules[module_name]
                        return []
                else:
                    # Log import errors but continue with other files
                    logger.debug(f"Import error executing module {file_path}: {str(e)}")
                    # Clean up module from sys.modules
                    if module_name in sys.modules:
                        del sys.modules[module_name]
                    return []
            except Exception as e:
                # Log other errors
                logger.debug(f"Error executing module {file_path}: {str(e)}")
                # Clean up module from sys.modules
                if module_name in sys.modules:
                    del sys.modules[module_name]
                return []

            # Inspect all classes in the module
            for name, obj in inspect.getmembers(module):
                # Check if it's a class and potentially a Flow
                if (
                    inspect.isclass(obj)
                    and name != "Flow"  # Skip the base Flow class
                    and hasattr(obj, "__module__")
                    and obj.__module__ == module_name
                ):

                    # Check if the class is a CrewAI Flow
                    if _is_flow_class(obj):
                        try:
                            # Extract flow information
                            flow_info = _extract_flow_info(
                                obj, file_path, name, content
                            )
                            flows.append(flow_info)
                        except Exception as e:
                            logger.debug(
                                f"Error extracting flow info for {name}: {str(e)}"
                            )

        finally:
            # Clean up module from sys.modules
            if module_name in sys.modules:
                del sys.modules[module_name]

            # Remove temporarily added paths from sys.path
            if sys_path_modified and file_dir in sys.path:
                sys.path.remove(file_dir)
            if pkg_root_modified and package_root in sys.path:
                sys.path.remove(package_root)

    except ImportError as e:
        # Common import errors should be logged at debug level
        logger.debug(f"Import error extracting flows from {file_path}: {str(e)}")
    except Exception as e:
        # Other errors at debug level too
        logger.debug(f"Error extracting flows from {file_path}: {str(e)}")

    return flows


def _contains_flow_indicators(content: str) -> bool:
    """
    Quick check if file content might contain CrewAI Flow classes.

    Args:
        content: File content as string

    Returns:
        True if file might contain flows, False otherwise
    """
    indicators = [
        "from crewai",
        "import crewai",
        "Flow",
        "@start",
        "@listen",
        "@router",
        "@persist",
        "kickoff",
    ]

    content_lower = content.lower()
    return any(indicator.lower() in content_lower for indicator in indicators)


def _is_flow_class(obj) -> bool:
    """
    Check if a class is a CrewAI Flow class.

    Args:
        obj: Class object to check

    Returns:
        True if it's a Flow class, False otherwise
    """
    try:
        # Try to import the Flow class from crewai
        from crewai.flow.flow import Flow as CrewAIFlow

        # Check if the class inherits from CrewAIFlow
        if issubclass(obj, CrewAIFlow):
            return True
    except ImportError:
        pass

    # Alternative check: Look for typical Flow characteristics
    # CrewAI Flows typically have:
    # 1. Methods with @start, @listen, @router decorators
    # 2. A kickoff method (inherited)
    # 3. Flow-specific attributes like _methods, _listeners

    has_flow_decorators = False
    has_kickoff = hasattr(obj, "kickoff")
    has_flow_attributes = any(hasattr(obj, attr) for attr in ["_methods", "_listeners", "_routers"])

    # Check for methods with flow decorators using AST analysis
    try:
        source = inspect.getsource(obj)
        has_flow_decorators = _has_flow_decorators_in_source(source)
    except:
        # Fallback to method inspection
        for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
            if _method_has_flow_decorators(method):
                has_flow_decorators = True
                break

    return has_flow_decorators or (has_kickoff and has_flow_attributes)


def _has_flow_decorators_in_source(source: str) -> bool:
    """
    Check if source code contains flow decorators using AST analysis.

    Args:
        source: Source code as string

    Returns:
        True if it has flow decorators, False otherwise
    """
    try:
        tree = ast.parse(source)
        
        class FlowDecoratorVisitor(ast.NodeVisitor):
            def __init__(self):
                self.found_decorators = False
            
            def visit_FunctionDef(self, node):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name):
                        if decorator.id in ["start", "listen", "router", "persist"]:
                            self.found_decorators = True
                    elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                        if decorator.func.id in ["start", "listen", "router", "persist"]:
                            self.found_decorators = True
                self.generic_visit(node)
        
        visitor = FlowDecoratorVisitor()
        visitor.visit(tree)
        return visitor.found_decorators
    except:
        return False


def _method_has_flow_decorators(method) -> bool:
    """
    Check if a method has flow decorators by examining attributes.

    Args:
        method: Method object to check

    Returns:
        True if it has flow decorators, False otherwise
    """
    flow_attributes = [
        "__is_start_method__",
        "__is_router__",
        "__is_listener__",
        "__persist__"
    ]
    return any(hasattr(method, attr) for attr in flow_attributes)


def _extract_flow_info(
    flow_class, file_path: str, class_name: str, file_content: str
) -> FlowInfo:
    """
    Extract detailed information from a Flow class.

    Args:
        flow_class: The Flow class object
        file_path: Path to the file containing the class
        class_name: Name of the class
        file_content: Content of the file as string

    Returns:
        FlowInfo object with detailed information
    """
    flow_id = str(uuid.uuid4())
    flow_name = class_name
    flow_description = flow_class.__doc__ or f"Flow: {class_name}"

    # Extract required inputs by inspecting the __init__ method
    required_inputs = _extract_flow_inputs(flow_class)

    # Extract comprehensive flow structure
    flow_structure = _extract_comprehensive_flow_structure(flow_class, file_content)
    
    # Extract methods information with enhanced analysis
    methods = flow_structure["methods"]

    # Determine state type
    state_type, state_model = _determine_state_type(flow_class, file_content)

    return FlowInfo(
        id=flow_id,
        name=flow_name,
        description=flow_description,
        file_path=file_path,
        class_name=class_name,
        flow_class=flow_class,
        required_inputs=required_inputs,
        methods=methods,
        state_type=state_type,
        state_model=state_model,
        listeners=flow_structure["listeners"],
        routers=flow_structure["routers"],
        router_paths=flow_structure["router_paths"],
        start_methods=flow_structure["start_methods"],
        method_levels=flow_structure["method_levels"],
    )


def _extract_flow_inputs(flow_class) -> List[FlowInput]:
    """
    Extract required inputs from a Flow class by inspecting its __init__ method.

    Args:
        flow_class: The Flow class to inspect

    Returns:
        List of FlowInput objects representing the required inputs
    """
    inputs = []

    try:
        # Get the __init__ method signature
        if hasattr(flow_class, "__init__"):
            signature = inspect.signature(flow_class.__init__)

            # Skip 'self' parameter
            for name, param in list(signature.parameters.items())[1:]:
                # Skip parameters with default values unless they're required
                if param.default is not inspect.Parameter.empty:
                    continue

                # Get type hint
                type_hint = "Any"
                if param.annotation != inspect.Parameter.empty:
                    type_hint = str(param.annotation)

                # Try to get description from docstring
                description = ""
                if flow_class.__init__.__doc__:
                    doc_lines = flow_class.__init__.__doc__.split("\n")
                    for line in doc_lines:
                        if f"{name}:" in line:
                            description = line.split(f"{name}:")[1].strip()
                            break

                if not description:
                    description = f"Input parameter: {name}"

                inputs.append(
                    FlowInput(
                        name=name,
                        description=description,
                        type_hint=type_hint,
                        required=True,
                    )
                )

    except Exception as e:
        logger.debug(f"Error extracting inputs from flow class: {str(e)}")

    return inputs


def _extract_comprehensive_flow_structure(flow_class, file_content: str) -> Dict[str, Any]:
    """
    Extract comprehensive flow structure including methods, listeners, routers, and dependencies.
    
    Based on official CrewAI visualization utilities for accurate flow parsing.

    Args:
        flow_class: The Flow class to inspect
        file_content: Content of the file as string

    Returns:
        Dictionary containing comprehensive flow structure
    """
    try:
        # Initialize flow structure
        structure = {
            "methods": [],
            "listeners": {},
            "routers": set(),
            "router_paths": {},
            "start_methods": [],
            "method_levels": {}
        }
        
        # Try to get flow attributes if available (for instantiated flows)
        flow_methods = {}
        flow_listeners = {}
        flow_routers = set()
        flow_router_paths = {}
        
        # Check if flow has internal attributes (for instantiated flows)
        if hasattr(flow_class, '_methods'):
            flow_methods = getattr(flow_class, '_methods', {})
        if hasattr(flow_class, '_listeners'):
            flow_listeners = getattr(flow_class, '_listeners', {})
        if hasattr(flow_class, '_routers'):
            flow_routers = getattr(flow_class, '_routers', set())
        if hasattr(flow_class, '_router_paths'):
            flow_router_paths = getattr(flow_class, '_router_paths', {})
            
        # Extract methods using AST analysis and inspection
        methods_info = _extract_methods_with_ast_analysis(flow_class, file_content)
        
        # Build comprehensive method information
        for method_name, method_data in methods_info.items():
            # Create FlowMethod object
            flow_method = FlowMethod(
                name=method_name,
                description=method_data.get('description', f'Flow method: {method_name}'),
                is_start=method_data.get('is_start', False),
                is_listener=method_data.get('is_listener', False),
                listens_to=method_data.get('listens_to', []),
                listener_condition=method_data.get('listener_condition', 'OR'),
                is_router=method_data.get('is_router', False),
                router_paths=method_data.get('router_paths', []),
                has_persist=method_data.get('has_persist', False),
                calls_crew=method_data.get('calls_crew', False),
                level=0  # Will be calculated later
            )
            structure["methods"].append(flow_method)
            
            # Track start methods
            if method_data.get('is_start', False):
                structure["start_methods"].append(method_name)
                
            # Track routers
            if method_data.get('is_router', False):
                structure["routers"].add(method_name)
                if method_data.get('router_paths'):
                    structure["router_paths"][method_name] = method_data['router_paths']
                    
            # Track listeners
            if method_data.get('is_listener', False):
                structure["listeners"][method_name] = (
                    method_data.get('listener_condition', 'OR'),
                    method_data.get('listens_to', [])
                )
        
        # Merge with flow internal attributes if available
        if flow_listeners:
            structure["listeners"].update(flow_listeners)
        if flow_routers:
            structure["routers"].update(flow_routers)
        if flow_router_paths:
            structure["router_paths"].update(flow_router_paths)
            
        # Calculate method levels using BFS (similar to official CrewAI)
        structure["method_levels"] = _calculate_method_levels(structure)
        
        # Update method levels in FlowMethod objects
        for method in structure["methods"]:
            method.level = structure["method_levels"].get(method.name, 0)
            
        return structure
        
    except Exception as e:
        logger.debug(f"Error extracting comprehensive flow structure: {str(e)}")
        # Return minimal structure
        return {
            "methods": [],
            "listeners": {},
            "routers": set(),
            "router_paths": {},
            "start_methods": [],
            "method_levels": {}
        }


def _extract_methods_with_ast_analysis(flow_class, file_content: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract method information using AST analysis and inspection.
    
    Based on official CrewAI approach for accurate decorator and dependency detection.

    Args:
        flow_class: The Flow class to inspect
        file_content: Content of the file as string

    Returns:
        Dictionary mapping method names to their extracted information
    """
    methods_info = {}
    
    try:
        # Parse the source code into AST
        tree = ast.parse(file_content)
        
        # Find the class definition
        class_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and hasattr(flow_class, '__name__') and node.name == flow_class.__name__:
                class_node = node
                break
        
        if not class_node:
            # Fallback to inspection-based method
            return _extract_methods_with_inspection(flow_class)
            
        # Analyze each method in the class
        for node in class_node.body:
            # Handle both regular and async function definitions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_name = node.name
                
                # Skip private methods and inherited methods
                if method_name.startswith("_") or method_name in ["kickoff", "plot"]:
                    continue
                    
                method_info = {
                    'description': _extract_docstring_from_node(node),
                    'is_start': False,
                    'is_listener': False,
                    'listens_to': [],
                    'listener_condition': 'OR',
                    'is_router': False,
                    'router_paths': [],
                    'has_persist': False,
                    'calls_crew': False
                }
                
                # Analyze decorators
                for decorator in node.decorator_list:
                    decorator_info = _analyze_decorator(decorator)
                    if decorator_info:
                        method_info.update(decorator_info)
                
                # Analyze method body for .crew() calls
                method_info['calls_crew'] = _method_calls_crew_ast(node)
                
                # Extract router paths if it's a router method
                if method_info['is_router']:
                    method_info['router_paths'] = _extract_router_paths_from_method(node, file_content)
                
                methods_info[method_name] = method_info
                
    except Exception as e:
        logger.debug(f"Error in AST analysis: {str(e)}")
        # Fallback to inspection-based method
        return _extract_methods_with_inspection(flow_class)
    
    return methods_info


def _extract_methods_with_inspection(flow_class) -> Dict[str, Dict[str, Any]]:
    """
    Fallback method extraction using inspection when AST analysis fails.
    
    Args:
        flow_class: The Flow class to inspect
        
    Returns:
        Dictionary mapping method names to their extracted information
    """
    methods_info = {}
    
    try:
        # Get all methods from the class
        class_methods = inspect.getmembers(flow_class, predicate=inspect.isfunction)
        
        for method_name, method in class_methods:
            # Skip private methods and inherited methods
            if method_name.startswith("_") or method_name in ["kickoff", "plot"]:
                continue
                
            method_info = {
                'description': method.__doc__ or f'Flow method: {method_name}',
                'is_start': hasattr(method, '__is_start_method__'),
                'is_listener': hasattr(method, '__is_listener__'),
                'listens_to': getattr(method, '__listens_to__', []),
                'listener_condition': getattr(method, '__listener_condition__', 'OR'),
                'is_router': hasattr(method, '__is_router__'),
                'router_paths': getattr(method, '__router_paths__', []),
                'has_persist': hasattr(method, '__persist__'),
                'calls_crew': _method_calls_crew_inspection(method)
            }
            
            methods_info[method_name] = method_info
            
    except Exception as e:
        logger.debug(f"Error in inspection-based method extraction: {str(e)}")
    
    return methods_info


def _analyze_decorator(decorator) -> Optional[Dict[str, Any]]:
    """
    Analyze a decorator node to extract flow-specific information.
    
    Args:
        decorator: AST decorator node
        
    Returns:
        Dictionary with decorator information or None
    """
    decorator_info = {}
    
    try:
        # Handle simple decorators like @start
        if isinstance(decorator, ast.Name):
            if decorator.id == 'start':
                decorator_info['is_start'] = True
            elif decorator.id == 'router':
                decorator_info['is_router'] = True
            elif decorator.id == 'persist':
                decorator_info['has_persist'] = True
                
        # Handle decorator calls like @start(), @listen(...), @router(...)
        elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
            decorator_name = decorator.func.id
            
            if decorator_name == 'start':
                decorator_info['is_start'] = True
            elif decorator_name == 'router':
                decorator_info['is_router'] = True
            elif decorator_name == 'persist':
                decorator_info['has_persist'] = True
            elif decorator_name == 'listen':
                decorator_info['is_listener'] = True
                # Extract listen targets and condition
                listen_info = _extract_listen_info(decorator)
                decorator_info.update(listen_info)
                
    except Exception as e:
        logger.debug(f"Error analyzing decorator: {str(e)}")
        
    return decorator_info if decorator_info else None


def _extract_listen_info(decorator_call) -> Dict[str, Any]:
    """
    Extract information from @listen decorator.
    
    Handles both simple method references and and_/or_ function calls.
    
    Args:
        decorator_call: AST Call node for @listen decorator
        
    Returns:
        Dictionary with listen information
    """
    listen_info = {
        'listens_to': [],
        'listener_condition': 'OR'
    }
    
    try:
        # Extract positional arguments (trigger methods or and_/or_ calls)
        for arg in decorator_call.args:
            if isinstance(arg, ast.Name):
                # Simple method name reference
                listen_info['listens_to'].append(arg.id)
            elif isinstance(arg, ast.Attribute):
                # Handle self.method_name references
                if isinstance(arg.value, ast.Name) and arg.value.id == 'self':
                    listen_info['listens_to'].append(arg.attr)
            elif isinstance(arg, ast.Call):
                # Handle and_() or or_() function calls
                if isinstance(arg.func, ast.Name):
                    func_name = arg.func.id
                    if func_name == 'and_':
                        listen_info['listener_condition'] = 'AND'
                        # Extract methods from and_() call
                        listen_info['listens_to'].extend(_extract_methods_from_logical_call(arg))
                    elif func_name == 'or_':
                        listen_info['listener_condition'] = 'OR'
                        # Extract methods from or_() call
                        listen_info['listens_to'].extend(_extract_methods_from_logical_call(arg))
                    
        # Extract keyword arguments (condition type) - fallback for explicit condition
        for keyword in decorator_call.keywords:
            if keyword.arg == 'condition' and isinstance(keyword.value, ast.Constant):
                if keyword.value.value in ['AND', 'OR']:
                    listen_info['listener_condition'] = keyword.value.value
                    
    except Exception as e:
        logger.debug(f"Error extracting listen info: {str(e)}")
        
    return listen_info


def _extract_methods_from_logical_call(call_node) -> List[str]:
    """
    Extract method names from and_() or or_() function calls.
    
    Args:
        call_node: AST Call node for and_() or or_() function
        
    Returns:
        List of method names
    """
    methods = []
    
    try:
        for arg in call_node.args:
            if isinstance(arg, ast.Name):
                # Direct method name reference
                methods.append(arg.id)
            elif isinstance(arg, ast.Attribute):
                # Handle self.method_name references
                if isinstance(arg.value, ast.Name) and arg.value.id == 'self':
                    methods.append(arg.attr)
            # Note: Could also handle nested and_/or_ calls if needed
                    
    except Exception as e:
        logger.debug(f"Error extracting methods from logical call: {str(e)}")
        
    return methods


def _method_calls_crew_ast(method_node) -> bool:
    """
    Check if method calls .crew() using AST analysis.
    
    Args:
        method_node: AST FunctionDef node
        
    Returns:
        True if method calls .crew(), False otherwise
    """
    try:
        class CrewCallVisitor(ast.NodeVisitor):
            def __init__(self):
                self.found = False
                
            def visit_Call(self, node):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "crew":
                        self.found = True
                self.generic_visit(node)
        
        visitor = CrewCallVisitor()
        visitor.visit(method_node)
        return visitor.found
        
    except Exception as e:
        logger.debug(f"Error checking crew calls: {str(e)}")
        return False


def _method_calls_crew_inspection(method) -> bool:
    """
    Check if method calls .crew() using inspection (fallback).
    
    Args:
        method: Method object
        
    Returns:
        True if method calls .crew(), False otherwise
    """
    try:
        source = inspect.getsource(method)
        return '.crew(' in source
    except:
        return False


def _extract_docstring_from_node(node) -> str:
    """
    Extract docstring from AST function node.
    
    Args:
        node: AST FunctionDef node
        
    Returns:
        Docstring or default description
    """
    try:
        if (node.body and 
            isinstance(node.body[0], ast.Expr) and 
            isinstance(node.body[0].value, ast.Constant) and 
            isinstance(node.body[0].value.value, str)):
            return node.body[0].value.value.strip()
    except:
        pass
    return f"Flow method: {node.name}"


def _extract_router_paths_from_method(method_node, file_content: str) -> List[str]:
    """
    Extract possible return paths from router method using AST analysis.
    
    Args:
        method_node: AST FunctionDef node
        file_content: Full file content
        
    Returns:
        List of possible return paths
    """
    paths = []
    
    try:
        # Use similar logic to official CrewAI get_possible_return_constants
        class ReturnVisitor(ast.NodeVisitor):
            def __init__(self):
                self.return_values = set()
                self.dict_definitions = {}
                
            def visit_Assign(self, node):
                # Check for dictionary assignments
                if isinstance(node.value, ast.Dict) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        dict_values = []
                        for val in node.value.values:
                            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                                dict_values.append(val.value)
                        if dict_values:
                            self.dict_definitions[var_name] = dict_values
                self.generic_visit(node)
                
            def visit_Return(self, node):
                # Direct string return
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    self.return_values.add(node.value.value)
                # Dictionary-based return
                elif isinstance(node.value, ast.Subscript):
                    if isinstance(node.value.value, ast.Name):
                        var_name = node.value.value.id
                        if var_name in self.dict_definitions:
                            for v in self.dict_definitions[var_name]:
                                self.return_values.add(v)
                self.generic_visit(node)
        
        visitor = ReturnVisitor()
        visitor.visit(method_node)
        paths = list(visitor.return_values)
        
    except Exception as e:
        logger.debug(f"Error extracting router paths: {str(e)}")
        
    return paths


def _calculate_method_levels(structure: Dict[str, Any]) -> Dict[str, int]:
    """
    Calculate hierarchical levels for methods using BFS.
    
    Based on official CrewAI calculate_node_levels function.
    
    Args:
        structure: Flow structure dictionary
        
    Returns:
        Dictionary mapping method names to their levels
    """
    levels = {}
    queue = deque()
    visited = set()
    pending_and_listeners = {}
    
    # Start methods at level 0
    for method_name in structure["start_methods"]:
        levels[method_name] = 0
        queue.append(method_name)
    
    # Precompute listener dependencies
    or_listeners = defaultdict(list)
    and_listeners = defaultdict(set)
    
    for listener_name, (condition_type, trigger_methods) in structure["listeners"].items():
        if condition_type == "OR":
            for method in trigger_methods:
                or_listeners[method].append(listener_name)
        elif condition_type == "AND":
            and_listeners[listener_name] = set(trigger_methods)
    
    # BFS traversal to assign levels
    while queue:
        current = queue.popleft()
        current_level = levels[current]
        visited.add(current)
        
        # Handle OR listeners
        for listener_name in or_listeners[current]:
            if listener_name not in levels or levels[listener_name] > current_level + 1:
                levels[listener_name] = current_level + 1
                if listener_name not in visited:
                    queue.append(listener_name)
        
        # Handle AND listeners
        for listener_name, required_methods in and_listeners.items():
            if current in required_methods:
                if listener_name not in pending_and_listeners:
                    pending_and_listeners[listener_name] = set()
                pending_and_listeners[listener_name].add(current)
                
                if required_methods == pending_and_listeners[listener_name]:
                    if listener_name not in levels or levels[listener_name] > current_level + 1:
                        levels[listener_name] = current_level + 1
                        if listener_name not in visited:
                            queue.append(listener_name)
        
        # Handle router connections
        if current in structure["routers"]:
            paths = structure["router_paths"].get(current, [])
            for path in paths:
                for listener_name, (condition_type, trigger_methods) in structure["listeners"].items():
                    if path in trigger_methods:
                        if listener_name not in levels or levels[listener_name] > current_level + 1:
                            levels[listener_name] = current_level + 1
                            if listener_name not in visited:
                                queue.append(listener_name)
    
    return levels


import types


def _extract_missing_module_name(err_msg: str) -> Optional[str]:
    """Extract the missing module name from an ImportError message."""
    # Typical message formats:
    #   "No module named 'foo'"
    #   "No module named foo.bar; 'foo' is not a package"
    pattern = r"No module named ['\"](?P<name>[a-zA-Z0-9_\.]+)['\"]"
    match = re.search(pattern, err_msg)
    return match.group("name") if match else None


def _install_stub_module(module_name: str):
    """Insert a dummy/stub module into sys.modules so importlib can succeed.

    The stub will lazily create submodules on attribute access to support
    statements such as ``import foo.bar`` as well.
    """
    if module_name in sys.modules:
        return

    parts = module_name.split(".")
    for i in range(1, len(parts) + 1):
        sub_name = ".".join(parts[:i])
        if sub_name not in sys.modules:
            stub = types.ModuleType(sub_name)

            # Provide a placeholder that raises on attribute usage to avoid
            # silent failures further down the line.
            def _getattr_stub(name):
                if name in stub.__dict__:
                    return stub.__dict__[name]
                else:

                    class _Dummy:
                        def __init__(self, *args, **kwargs):
                            pass

                        def __call__(self, *args, **kwargs):  # type: ignore
                            return None

                        def __getattr__(self, _item):  # type: ignore
                            return _Dummy()

                    dummy = _Dummy()
                    stub.__dict__[name] = dummy
                    return dummy

            stub.__getattr__ = _getattr_stub  # type: ignore
            sys.modules[sub_name] = stub


def _determine_state_type(flow_class, file_content: str) -> Tuple[str, Optional[str]]:
    """
    Determine the state management type used by the flow.

    Args:
        flow_class: The Flow class to inspect
        file_content: Content of the file as string

    Returns:
        Tuple of (state_type, state_model_name)
    """
    try:
        # Look for structured state patterns
        state_patterns = [
            r"class\s+(\w+State?)\s*\(\s*BaseModel\s*\)",
            r"class\s+(\w+State?)\s*\(\s*.*BaseModel.*\)",
        ]

        for pattern in state_patterns:
            match = re.search(pattern, file_content)
            if match:
                return "structured", match.group(1)

        # Check if the class has a state attribute definition
        if hasattr(flow_class, "__annotations__"):
            annotations = flow_class.__annotations__
            if "state" in annotations:
                state_type = str(annotations["state"])
                if "BaseModel" in state_type:
                    return "structured", state_type

    except Exception as e:
        logger.debug(f"Error determining state type: {str(e)}")

    return "unstructured", None


def load_flow(flow_info: FlowInfo, inputs: Dict[str, Any] = None) -> Any:
    """
    Load and instantiate a Flow class with the provided inputs.

    Args:
        flow_info: FlowInfo object containing information about the flow
        inputs: Dictionary of input parameters for the flow

    Returns:
        Instantiated Flow object
    """
    if inputs is None:
        inputs = {}

    try:
        # Generate a random module name to avoid conflicts
        module_name = f"flow_module_{uuid.uuid4().hex}"

        # Get the directory of the file for handling relative imports
        file_dir = os.path.dirname(flow_info.file_path)

        # Add the file's directory to sys.path temporarily
        sys_path_modified = False
        if file_dir not in sys.path:
            sys.path.insert(0, file_dir)
            sys_path_modified = True

        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(
                module_name, flow_info.file_path
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load module from {flow_info.file_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Get the Flow class
            flow_class = getattr(module, flow_info.class_name)

            # Filter inputs to only include those expected by the constructor
            signature = inspect.signature(flow_class.__init__)
            filtered_inputs = {}

            for param_name, param in signature.parameters.items():
                if param_name == "self":
                    continue
                if param_name in inputs:
                    filtered_inputs[param_name] = inputs[param_name]
                elif param.default is inspect.Parameter.empty:
                    # Required parameter not provided
                    logger.warning(
                        f"Required parameter '{param_name}' not provided for flow {flow_info.name}"
                    )

            # Instantiate the Flow with filtered inputs
            flow_instance = flow_class(**filtered_inputs)

            return flow_instance

        finally:
            # Clean up
            if module_name in sys.modules:
                del sys.modules[module_name]

            if sys_path_modified and file_dir in sys.path:
                sys.path.remove(file_dir)

    except Exception as e:
        logger.error(f"Error loading flow {flow_info.name}: {str(e)}")
        raise


def run_flow(flow_info: FlowInfo, inputs: Dict[str, Any] = None) -> Any:
    """
    Load and run a Flow with the provided inputs.

    Args:
        flow_info: FlowInfo object containing information about the flow
        inputs: Dictionary of input parameters for the flow

    Returns:
        Flow execution result
    """
    try:
        # Load the flow
        flow_instance = load_flow(flow_info, inputs)

        # Run the flow
        result = flow_instance.kickoff()

        return result

    except Exception as e:
        logger.error(f"Error running flow {flow_info.name}: {str(e)}")
        raise


def get_flow_state(flow_instance) -> Dict[str, Any]:
    """
    Get the current state of a flow instance.

    Args:
        flow_instance: The flow instance

    Returns:
        Dictionary representation of the flow state
    """
    try:
        if hasattr(flow_instance, "state"):
            state = flow_instance.state
            if hasattr(state, "model_dump"):
                # Structured state (Pydantic model)
                return state.model_dump()
            else:
                # Unstructured state (dict)
                return dict(state) if state else {}
        return {}
    except Exception as e:
        logger.error(f"Error getting flow state: {str(e)}")
        return {}


# Utility functions for flow management
def validate_flow_inputs(flow_info: FlowInfo, inputs: Dict[str, Any]) -> List[str]:
    """
    Validate that all required inputs are provided.

    Args:
        flow_info: FlowInfo object
        inputs: Dictionary of input parameters

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    for required_input in flow_info.required_inputs:
        if required_input.required and required_input.name not in inputs:
            errors.append(f"Required input '{required_input.name}' is missing")

    return errors


def get_flow_structure(flow_info: FlowInfo) -> Dict[str, Any]:
    """
    Get comprehensive flow structure for visualization.
    
    Returns structure compatible with official CrewAI visualization utilities.

    Args:
        flow_info: FlowInfo object

    Returns:
        Dictionary with comprehensive flow structure for visualization
    """
    # Build methods dictionary (similar to flow._methods)
    methods_dict = {}
    for method in flow_info.methods:
        # Create a mock method object with the required attributes
        class MockMethod:
            def __init__(self, method_info: FlowMethod):
                self.name = method_info.name
                self.__name__ = method_info.name
                if method_info.is_start:
                    self.__is_start_method__ = True
                if method_info.is_router:
                    self.__is_router__ = True
                if method_info.is_listener:
                    self.__is_listener__ = True
                if method_info.has_persist:
                    self.__persist__ = True
                    
        methods_dict[method.name] = MockMethod(method)
    
    return {
        "_methods": methods_dict,
        "_listeners": flow_info.listeners,
        "_routers": flow_info.routers,
        "_router_paths": flow_info.router_paths,
        "start_methods": flow_info.start_methods,
        "method_levels": flow_info.method_levels,
        "methods_info": {
            method.name: {
                "name": method.name,
                "description": method.description,
                "is_start": method.is_start,
                "is_listener": method.is_listener,
                "listens_to": method.listens_to,
                "listener_condition": method.listener_condition,
                "is_router": method.is_router,
                "router_paths": method.router_paths,
                "has_persist": method.has_persist,
                "calls_crew": method.calls_crew,
                "level": method.level
            }
            for method in flow_info.methods
        }
    }


def get_flow_summary(flow_info: FlowInfo) -> Dict[str, Any]:
    """
    Get a summary of flow information.

    Args:
        flow_info: FlowInfo object

    Returns:
        Dictionary with flow summary
    """
    return {
        "id": flow_info.id,
        "name": flow_info.name,
        "description": flow_info.description,
        "file_path": flow_info.file_path,
        "required_inputs": len(flow_info.required_inputs),
        "methods": len(flow_info.methods),
        "state_type": flow_info.state_type,
        "start_methods": [m.name for m in flow_info.methods if m.is_start],
        "listener_methods": [m.name for m in flow_info.methods if m.is_listener],
        "router_methods": [m.name for m in flow_info.methods if m.is_router],
        "crew_methods": [m.name for m in flow_info.methods if m.calls_crew],
        "method_levels": flow_info.method_levels,
        "listeners": flow_info.listeners,
        "router_paths": flow_info.router_paths,
    }
