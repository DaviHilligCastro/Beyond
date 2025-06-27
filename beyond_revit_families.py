"""
O script busca as famílias Revit (.rfa) da Beyond Domotics
em um projeto MEP e executa bateria de testes.

Uso:
    Rotina Dynamo - beyond_verification.dyn.

Saída:
    Retorna as informações do teste em um log de texto
    gravado na raiz do projeto Revit.

Requisitos:
    - CPython3;
    - Revit 2025.
"""
__title__ = "Beyond Revit Family Verification"
__description__ = "Performs a test suite on electrical Revit Families for beyond.dm products"
__version__ = "1.0.0"
__status__ = "Development" 
__license__ = "MIT"
__date__ = "2025-06-25"
__updated__ = ""
__author__ = "Davi Hillig Castro"
__email__ = "davihillig@gmail.com"
__maintainer__ = "Davi Hillig Castro"
__url__ = ""

#===================================================================================================================
#==========================         IMPORTS          ===============================================================
#===================================================================================================================

import clr
import os
from abc import ABC, abstractmethod
from datetime import datetime

clr.AddReference("RevitNodes")
import Revit
import Revit.Elements
clr.ImportExtensions(Revit.Elements)

clr.AddReference("RevitServices")
import RevitServices
from RevitServices.Persistence import DocumentManager 
from RevitServices.Transactions import TransactionManager 

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import Autodesk 
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

#===================================================================================================================
#==========================         ABSTRACT CLASSES          ======================================================
#===================================================================================================================

class ElectricalDataDelivery(ABC):
    @abstractmethod
    def _get_electrical_connector(self):
        pass

    @abstractmethod
    def _get_mep_connector_info(self):
        pass

    @abstractmethod
    def get_connector_parameter_value(self, parameter_key, mep_connector_info):
        pass

    @abstractmethod
    def get_family_parameter_value(self, parameter_key):
        pass

    @abstractmethod
    def convert_to_volts(self, internal_value):
        pass

    @abstractmethod
    def convert_to_watts(self, internal_value):
        pass

#===================================================================================================================
#==========================         IO COMPONENT - COMPONENTE DE SAÍDAS          ===================================
#===================================================================================================================

class BeyondParameterSetter():

    def __init__(self, beyond_device):
        self.beyond = beyond_device

    def set_family_parameters(self):
        
        location = self.beyond.family_instance.LookupParameter("Beyond.LocalDeInstalação")
        device_id = self.beyond.family_instance.LookupParameter("Beyond.IDObjeto")
        switch_id = self.beyond.family_instance.LookupParameter("Beyond.IDComandos")
        circuit_number = self.beyond.family_instance.LookupParameter("Beyond.NúmeroDoCircuito")
        panel = self.beyond.family_instance.LookupParameter("Beyond.PainelDistribuição")
        voltage = self.beyond.family_instance.LookupParameter("Beyond.Voltagem")
        number_of_poles = self.beyond.family_instance.LookupParameter("Beyond.NúmeroDePolos")
        apparent_load_channel_1 = self.beyond.family_instance.LookupParameter("Beyond.Iluminação.PotênciaAparente.Saída1")
        apparent_load_channel_2 = self.beyond.family_instance.LookupParameter("Beyond.Iluminação.PotênciaAparente.Saída2")
        apparent_load_channel_3 = self.beyond.family_instance.LookupParameter("Beyond.Iluminação.PotênciaAparente.Saída3")
        
        location.Set(self.beyond.space_or_room)
        device_id.Set(self.beyond.device_id)
        switch_id.Set(self.beyond.grouped_switch_id)
        circuit_number.Set(self.beyond.circuit_number)
        panel.Set(self.beyond.panel)
        voltage.Set(self.beyond.voltage)
        number_of_poles.Set(self.beyond.number_of_poles)
        apparent_load_channel_1.Set(self.beyond.output_channel_1.apparent_load)
        apparent_load_channel_2.Set(self.beyond.output_channel_2.apparent_load)
        apparent_load_channel_3.Set(self.beyond.output_channel_3.apparent_load)


class Logger:

    def __init__(self, doc, log_file_name):
        """
        Inicializa o logger com o nome do arquivo de log.
        O arquivo de log será salvo no mesmo diretório do documento do Revit.
        Args:
            log_file_name (str): Nome do logger.
        """
        self.log_file_name = log_file_name
        self.log_file_path = self._get_log_file_path_from_revit_document(doc)

    def _get_log_file_path_from_revit_document(self, doc):
        """
        Retorna o caminho do arquivo de log, no diretório do documento aberto na seção ativa do Revit.
        Args:
            doc: a instancia de DocumentManager.Instance.CurrentDBDocument
        Returns:
            caminho do arquivo : str
        """
        if doc.IsWorkshared:
            file_path = doc.GetWorksharingCentralModelPath()
            file_path = ModelPathUtils.ConvertModelPathToUserVisiblePath(file_path)
        else:
            file_path = doc.PathName

        document_directory = os.path.dirname(file_path)
        return os.path.join(document_directory, self.log_file_name)

    def write_to_log(self, message):
        """
        Adiciona uma nova mensagem ao arquivo de log.
        Se o arquivo não existir, ele será criado.
        Args:
            message (string): mensagem de log
        """
        timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        header = timestamp + " - Relatório de instalação Beyond"
        log_message = f"{header}\n\n{message}\n\n"

        with open(self.log_file_path, 'a') as logFile:
            logFile.write(log_message)
    
    @staticmethod
    def log_message(beyond_devices):
        """
        """
        if beyond_devices == None:
            return "Não há famílias Beyond instaladas no projeto."

        faulty_devices  = []
        working_devices = []
        
        for device in beyond_devices:
            log_issues = (" - " if device.issue_flag else "") + " / ".join(device.issues)
            log_entry = f"{device.device_id} - Id {device.revit_element_id}"
            (faulty_devices if device.issue_flag else working_devices).append(log_entry + log_issues)

        return (
            "Dispositivo(s) com instalação elétrica adequada:\n"
            + "\n".join(working_devices) + "\n\n"
            + "Dispositivo(s) com problemas de instalação elétrica no projeto:\n"
            + "\n".join(faulty_devices)
            )
        
#===================================================================================================================
#==========================         IO COMPONENT - COMPONENTE DE ENTRADAS          =================================
#===================================================================================================================

class ElectricalData(ElectricalDataDelivery):
    """
    Classe Relacionada a obtenção de parâmetros ElectricDomain no modelo Revit
    """
    def __init__(self, family_instance):
        self.family_instance = family_instance
        self.mep_connector_info = self._get_mep_connector_info()
    
    def _get_electrical_connector(self):
        """
        Obtém o conector elétrico de uma família assumindo que a mesma possua apenas um 
        conector de domínio elétrico.
        """
        if self.family_instance is None: return None
        
        mep_model = self.family_instance.MEPModel
        if mep_model is None: return None
        
        connector_manager = mep_model.ConnectorManager
        connector_set = connector_manager.Connectors
        connector_iterator = connector_set.ForwardIterator()
        while connector_iterator.MoveNext():
            connector = connector_iterator.Current
            if connector.Domain == Domain.DomainElectrical: return connector
        
        return None
        
    def _get_mep_connector_info(self):
        """
        """
        connector = self._get_electrical_connector()
        return connector.GetMEPConnectorInfo() if connector else None          

    def get_connector_parameter_value(self, parameter_key):

        parameters_dic = {
            "voltage"         : BuiltInParameter.RBS_ELEC_VOLTAGE,
            "number_of_poles" : BuiltInParameter.RBS_ELEC_NUMBER_OF_POLES,
            "apparent_load"   : BuiltInParameter.RBS_ELEC_APPARENT_LOAD
        }
        
        built_in_parameter = parameters_dic.get(parameter_key)
        parameter_value = self.mep_connector_info.GetConnectorParameterValue(ElementId(built_in_parameter)).Value
        
        if parameter_value == None:
            return None
        
        return parameter_value
    
    def get_family_parameter_value(self, parameter_key):
        parameters_dic = {
            "panel"          : BuiltInParameter.RBS_ELEC_CIRCUIT_PANEL_PARAM,
            "circuit_number" : BuiltInParameter.RBS_ELEC_CIRCUIT_NUMBER,
            "switch_id"      : BuiltInParameter.RBS_ELEC_SWITCH_ID_PARAM
        }
        
        built_in_parameter = parameters_dic.get(parameter_key)
        parameter_value = ParameterService.get_parameter_value(self.family_instance.get_Parameter(built_in_parameter))
        
        if parameter_value == "" or parameter_value == None:
            return "Nulo"
        
        return parameter_value

    def convert_to_volts(self, internal_value):
        volts_value = UnitUtils.ConvertFromInternalUnits(internal_value, UnitTypeId.Volts)
        return round(volts_value, 0)
        
    def convert_to_watts(self, internal_value):
        watts_value = UnitUtils.ConvertFromInternalUnits(internal_value, UnitTypeId.Watts)
        return round(watts_value, 0)


class ParameterService:

    def get_parameter_value(parameter):
        """
        Recupera o valor do objeto parâmetro de acordo com o StorageType.
        Args:
            parameter: Parâmetro Revit
        Returns:
            Parameter Value
        """
        value = None
        if parameter.StorageType == StorageType.Double:
            value = parameter.AsDouble()
        elif parameter.StorageType == StorageType.Integer:
            if parameter.Definition.ParameterType == ParameterType.Integer:
                value = parameter.AsInteger()
            else:     
                value = parameter.AsValueString()
        elif parameter.StorageType == StorageType.String:
            value = parameter.AsString()
        elif parameter.StorageType == StorageType.ElementId:
            value = parameter.AsElementId()
        
        return value
    
#===================================================================================================================
#==========================         USE  C A S E 1        ==========================================================
#===================================================================================================================

class LightingFixture:
    """
    Classe relativa às luminárias instaladas no Modelo.
    """
    def __init__(self, lighting_fixture, electrical_data: ElectricalDataDelivery):
        if lighting_fixture is None: return None
            
        self.family_instance = lighting_fixture
        self.electrical_data = electrical_data
        self.panel = electrical_data.get_family_parameter_value("panel")
        self.circuit_number = electrical_data.get_family_parameter_value("circuit_number")
        self.switch_id = electrical_data.get_family_parameter_value("switch_id")                       
        self.apparent_load = electrical_data.get_connector_parameter_value("apparent_load")


class LightingService:

    @staticmethod
    def sum_apparent_load_by_switch_id(lighting_objects_list):
        """
        Calcula a carga aparente total para cada switch_id.
        Engine CPython de Dynamo não suporta dicionários, ou pelo menos tuplas como key. 
        Args:
            lighting_objects_list: Lista de dicionários ou objetos contendo informações das luminárias,
            incluindo panel, circuit_number, switch_id e apparent_load.
    
        Returns:
            Uma lista de listas com os dados de cada interruptor [[panel, circuit_number, switch_id, apparent_load], [], ...[]]
        """
        load_mapping = []
        for lighting_fixture in lighting_objects_list:
            
            channel_key = [lighting_fixture.panel, lighting_fixture.circuit_number, lighting_fixture.switch_id]
            apparent_load = lighting_fixture.apparent_load 
            
            if any(p == "Nulo" for p in channel_key) : continue

            found = False
            for properties in load_mapping:
                if properties[0] == channel_key[0] and properties[1] == channel_key[1] and properties[2] == channel_key[2]:
                    properties[3] += apparent_load
                    found = True
                    
            if not found:
                load_mapping.append([channel_key[0], channel_key[1], channel_key[2], apparent_load])

        return load_mapping


class LightingFactory:
    
    @staticmethod
    def create_lighting_fixtures(lighting_fixtures_collector):
        """
        Returns:
            Retorna uma lista de objetos LightingFixture
        """
        light_objects = []
        for family_instance in lighting_fixtures_collector:
            electrical_data = ElectricalData(family_instance)
            light_fixture = LightingFixture(family_instance, electrical_data)
            light_objects.append(light_fixture)
        return light_objects
        
    @staticmethod
    def get_apparent_load_by_switch_id(light_objects):
        
        return LightingService.sum_apparent_load_by_switch_id(light_objects)

#===================================================================================================================
#==========================         B E Y O N D  BUSINESS RULES          ===========================================
#===================================================================================================================

class BeyondService:

    """
    Contém a lógica de dados, comportamentos e validações para BeyondDevice
    """
    def __init__(self, beyond_object):

        self.instance = beyond_object

    def get_issue_flag(self):

        if self.instance.issues != []: self.instance.issue_flag = True
        return
    
    def check_device_panel(self):
        """
        Compara todos os valores de painel atribuídos pelo projetista para um mesmo dispositivo (4 conectoers elétricos na família),
        caso haja divergência, mensagem indicativa é retornada para issues.
        """
        channels_panel = [self.instance.output_channel_1.panel, self.instance.output_channel_2.panel, self.instance.output_channel_3.panel]
        dock_station_panel = self.instance.dock_station.panel  
        
        if any(panel != dock_station_panel for panel in channels_panel):   
            self.instance.issues.append("Divergência no painel")
            self.instance.panel = "Divergência no painel"
            return
        
        if dock_station_panel == "Nulo":
            self.instance.issues.append("Painel desconectado")
            self.instance.panel = "Desconectado"
            return
        
        self.instance.panel = self.instance.dock_station.panel
        return
    
    def check_device_circuit(self):
        """
        Compara todos os circuitos atribuídos pelo projetista para um mesmo dispositivo,
        caso haja divergência, mensagem indicativa é retornada para issues.
        """
        channels_circuit = [self.instance.output_channel_1.circuit_number, self.instance.output_channel_2.circuit_number, self.instance.output_channel_3.circuit_number]
        dock_station_circuit = self.instance.dock_station.circuit_number
        
        if any(circuit != dock_station_circuit for circuit in channels_circuit): 
            self.instance.issues.append("Divergência no circuito")
            self.instance.circuit_number = "Divergência no circuito"
            return
        
        if dock_station_circuit == "Nulo":
            self.instance.issues.append("Circuito desconectado")
            self.instance.circuit_number = "Desconectado"
            return
        
        self.instance.circuit_number = dock_station_circuit
        return
    
    def check_output_channel_load(self, channel_number):
        """
            
        """
        if channel_number == 1: channel = self.instance.output_channel_1
        if channel_number == 2: channel = self.instance.output_channel_2
        if channel_number == 3: channel = self.instance.output_channel_3
        
        apparent_load = channel.electrical_data.convert_to_watts(channel.apparent_load)
        switch_id     = channel.switch_id
        channel_name  = str(channel)
        
        message = []

        if switch_id == "Nulo":
            if message == []:
                message.append(f"{channel_name}")
            message.append("ID não atribuído")

        if switch_id != "Nulo" and apparent_load == 0:
            if message == []:
                message.append(f"{channel_name}")
            message.append(f"ID({switch_id}) carga nula")

        if apparent_load > 100:
            if message == []:
                message.append(f"{channel_name}:")
            message.append(f"ID({switch_id}) {apparent_load}VA")

        if message != []:
            self.instance.issues.append(" ".join(message))
            return

    def check_dock_station_load(self):
        """
            
        """
        dock_station_load = self.instance.dock_station.electrical_data.convert_to_watts(self.instance.dock_station.apparent_load)
        if dock_station_load == 0:
            self.instance.issues.append("Tomada com carga nula")
        
        if dock_station_load > 100:
            self.instance.issues.append("Tomada com carga excedida")
        
        return
          
    def assign_apparent_load_to_channel(self, channel_number, load_mapping):
        """
        Atribui a carga aparente calculada correspondente ao canal de saída.
        """
        channel = None
        if channel_number == 1: channel = self.instance.output_channel_1
        if channel_number == 2: channel = self.instance.output_channel_2
        if channel_number == 3: channel = self.instance.output_channel_3
        
        key = [channel.panel, channel.circuit_number, channel.switch_id]
        error_messages = ["Nulo", "Divergência no painel", "Divergência no circuito", "Desconectado"]

        if load_mapping == None:
            channel.apparent_load = 0
            return
        
        for error_type in error_messages:
            if any(e == error_type for e in key): 
                channel.apparent_load = 0
                return

        for entry in load_mapping:    
            if [entry[0], entry[1], entry[2]] == key:
                channel.apparent_load = entry[3]
                return

    def group_switch_ids(self):
        """
        Retorna uma string dos ids de interruptores para cada dispositivo
        Returns:
            switch_ids(string): [a, Nulo, c]
        """
        formatted_ids = [self.instance.output_channel_1.switch_id, self.instance.output_channel_2.switch_id, self.instance.output_channel_3.switch_id]
        return "[" + ", ".join(formatted_ids) + "]"
       
    def _get_space(self):
        """
        Obtém o Espaço associado a uma instância de família.
        Returns:
            Autodesk.Revit.DB.Mechanical.Space: O Espaço, se houver.
        """
        space = self.instance.family_instance.Space
        if space is not None:
            return space
            
        location = self.instance.family_instance.Location
        
        if isinstance(location, LocationPoint):
            space = doc.GetSpaceAtPoint(location.Point)
            return space
        
        return None

    def _get_room(self):
        """
        Retorna o Ambiente associado a uma instância de família.
        Returns:
            room_name(string):O Ambiente associado.
        """
        room = self.instance.family_instance.Room
        if room is not None:
            return room

        location = self.instance.family_instance.Location
        if isinstance(location, LocationPoint):
            room = doc.GetRoomAtPoint(location.Point)
            return room
        return None

    def get_space_or_room(self):
        """
        Verifica se há Espaço ou Ambiente associado a família
        Returns:
            valid_value(string): O nome do Espaço, Ambiente ou Mensagem indicaiva de valor Nulo.
        """
        space = self._get_space()
        if space != None:
            space_name = space.get_Parameter(BuiltInParameter.SPACE_NAME_PARAM)
            if space_name:
                return space_name.AsString()
        room = self._get_room()
        if room is not None and room != "":
            room_name = room.get_Parameter(BuiltInParameter.ROOM_NAME)
            if room_name:
                return room_name.AsString()
        return "Espaço ou Ambiente não atribuído"

#===================================================================================================================
#==========================         B E Y O N D  ENTITY          ===================================================
#===================================================================================================================

class BeyondDevice():
    """
    Relativa aos dispositivos da Beyond Domotics
    """
    count_devices = 0

    def __init__(self, beyond_family_instance):
        """
        Uma instância da classe utiliza as famílias de Revit Beyond.ONE ou Beyond.POWER e 
        suas subfamílias, recuperando informações do projeto para a instanciação.
        """
        if beyond_family_instance is not None:
            BeyondDevice.count_devices += 1
            self.service = BeyondService(self)
            self.family_instance = beyond_family_instance
            self.name = self.family_instance.Name
            self.revit_element_id = self.family_instance.Id
            self.device_id = self.device_id()
            self.dock_station = None
            self.output_channel_1 = None
            self.output_channel_2 = None
            self.output_channel_3 = None
            self.panel = None
            self.circuit_number = None
            self.voltage = None
            self.number_of_poles = None
            self.space_or_room = None
            self.grouped_switch_id = None
            self.issues = []
            self.issue_flag = False
    
    def __str__(self):
        return f"{self.family_instance.Name}"        
            
    def device_id (self):
        """
        Gera o identificador único interno
        Returns:
            device_id(string): Identificador beyond para cada dispositivo
        """       
        if BeyondDevice.count_devices <= 9:
            return "BDO" + str (BeyondDevice.count_devices)
        else:
            return "BD" + str (BeyondDevice.count_devices)

    def get_nested_families(self, nested_family_name):       
        """
        Recupera as famílias aninhadas na família principal.
        Args:
            nested_family_name(string): O nome da FamilySymbol, "Saída" ou "Beyond.Base"
        Returns:
            dock_station(FamilyInstance): 
            output_channels(List[FamilyInstance])
        """
        nested_families = []
        nested_element_ids = self.family_instance.GetDependentElements(ElementClassFilter(FamilyInstance))
        for id in nested_element_ids:
            
            nested_element = doc.GetElement(id)
            if nested_element.Name.startswith(nested_family_name):
                
                nested_families.append(nested_element)
        
        if   nested_family_name == "Beyond.Base" : return nested_families[0]
        elif nested_family_name == "Saída"       : return nested_families

    def initialize_components(self, lighting_load_mapping):
        
        dock_station_family = self.get_nested_families("Beyond.Base")
        self.dock_station = DockStation(dock_station_family, ElectricalData(dock_station_family))
        
        output_channel_families = self.get_nested_families("Saída")
        output_channel_1_family = output_channel_families[0]
        output_channel_2_family = output_channel_families[1]
        output_channel_3_family = output_channel_families[2]

        electrical_data_channel_1 = ElectricalData(output_channel_1_family)
        electrical_data_channel_2 = ElectricalData(output_channel_2_family)
        electrical_data_channel_3 = ElectricalData(output_channel_3_family)

        self.output_channel_1 = OutputChannel(output_channel_1_family, electrical_data_channel_1)
        self.output_channel_2 = OutputChannel(output_channel_2_family, electrical_data_channel_2)
        self.output_channel_3 = OutputChannel(output_channel_3_family, electrical_data_channel_3)
        
        self.service.check_device_panel()
        self.service.check_device_circuit()
        
        self.grouped_switch_id = self.service.group_switch_ids()
        self.voltage = self.dock_station.voltage
        self.number_of_poles = self.dock_station.number_of_poles
        self.space_or_room = self.service.get_space_or_room()

        self.service.assign_apparent_load_to_channel(1, lighting_load_mapping)
        self.service.assign_apparent_load_to_channel(2, lighting_load_mapping)
        self.service.assign_apparent_load_to_channel(3, lighting_load_mapping)

        self.service.check_dock_station_load()
        self.service.check_output_channel_load(1)
        self.service.check_output_channel_load(2)
        self.service.check_output_channel_load(3)

        self.service.get_issue_flag()

    
class DockStation:
    """
    Classe relativa aos dispositivos Base Beyond instalados no projeto.
    """
    def __init__(self, dock_station_family, electrical_data: ElectricalDataDelivery):

        if dock_station_family is not None:
            self.family_instance = dock_station_family
            self.electrical_data = electrical_data
            self.panel = self.electrical_data.get_family_parameter_value("panel")
            self.circuit_number = self.electrical_data.get_family_parameter_value("circuit_number")
            self.number_of_poles = self.electrical_data.get_connector_parameter_value("number_of_poles")
            self.voltage = self.electrical_data.get_connector_parameter_value("voltage")
            self.apparent_load = self.electrical_data.get_connector_parameter_value("apparent_load")

    def __str__(self):

        return f"{self.family_instance.Name}"


class OutputChannel:
    """
    Classe relativa às Saídas/Canais de iluminação Beyond instalados no projeto.
    """
    def __init__(self, output_channel_family, electrical_data: ElectricalDataDelivery):

        self.family_instance = output_channel_family
        self.electrical_data = electrical_data
        self.panel = self.electrical_data.get_family_parameter_value("panel")
        self.circuit_number = self.electrical_data.get_family_parameter_value("circuit_number")
        self.switch_id = self.electrical_data.get_family_parameter_value("switch_id")
        self.apparent_load = 0

    def __str__(self):

        return f"{self.family_instance.Name}"


class BeyondFactory():

    def create_devices(beyond_family_instances, lighting_load_mapping):
        
        beyond_objects = []
        for family_instance in beyond_family_instances:
            device = BeyondDevice(family_instance)
            device.initialize_components(lighting_load_mapping)
            beyond_objects.append(device)
        return beyond_objects

#===================================================================================================================
#==========================         M A I N          ===============================================================
#===================================================================================================================

#DOCUMENT AND APPLICATION
doc = DocumentManager.Instance.CurrentDBDocument
uiapp = DocumentManager.Instance.CurrentUIApplication
app = uiapp.Application
uidoc = uiapp.ActiveUIDocument

#===================================================================================================================
#COLLECTORS
electrical_fixtures_collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_ElectricalFixtures).WhereElementIsNotElementType().ToElements()
lighting_fixtures_collector = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_LightingFixtures).WhereElementIsNotElementType().ToElements()

#===================================================================================================================
#LIGHTING FIXTURES
try:
    if lighting_fixtures_collector is not []:
        lighting_fixtures = LightingFactory.create_lighting_fixtures(lighting_fixtures_collector)
        apparent_load_mapping = LightingFactory.get_apparent_load_by_switch_id(lighting_fixtures)
except:
    apparent_load_mapping = None

#===================================================================================================================
#BEYOND
beyond_families = list(filter(lambda x : x.Name == ("ONE.Black") or x.Name == ("ONE.White") or x.Name == ("POWER.Black") or x.Name == ("POWER.White"), electrical_fixtures_collector))
try:
    if beyond_families != []:

        beyond_objects = BeyondFactory.create_devices(beyond_families, apparent_load_mapping)
        
        #SET BEYOND FAMILY PARAMETERS
        t = Transaction(doc, "Set Beyond parameters")
        t.Start()
        for device in beyond_objects:
            setter = BeyondParameterSetter(device)
            setter.set_family_parameters()
        t.Commit()

except:
    beyond_objects = None

#===================================================================================================================
#Write to log
log = Logger(doc, "beyond_log.txt")
log_message = Logger.log_message(beyond_objects)
log.write_to_log(log_message)

#===================================================================================================================
OUT = [beyond_objects]