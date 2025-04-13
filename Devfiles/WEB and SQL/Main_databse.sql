-- Database: International Airport Management System

-- 1. Airlines Table
CREATE TABLE Airlines (
    AirlineID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Country VARCHAR(100) NOT NULL,
    ContactInfo VARCHAR(255)
);

-- 2. Flights Table
CREATE TABLE Flights (
    FlightID INT PRIMARY KEY,
    FlightNumber VARCHAR(10) UNIQUE NOT NULL,
    AirlineID INT,
    Source VARCHAR(100) NOT NULL,
    Destination VARCHAR(100) NOT NULL,
    DepartureTime DATETIME NOT NULL,
    ArrivalTime DATETIME NOT NULL,
    Status ENUM('Scheduled', 'Delayed', 'Cancelled', 'Completed') NOT NULL,
    FOREIGN KEY (AirlineID) REFERENCES Airlines(AirlineID)
);

-- 3. Passengers Table
CREATE TABLE Passengers (
    PassengerID INT PRIMARY KEY,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    DateOfBirth DATE NOT NULL,
    PassportNumber VARCHAR(20) UNIQUE NOT NULL,
    Nationality VARCHAR(50) NOT NULL,
    ContactInfo VARCHAR(255)
);

-- 4. Tickets Table
CREATE TABLE Tickets (
    TicketID INT PRIMARY KEY,
    FlightID INT,
    PassengerID INT,
    SeatNumber VARCHAR(5),
    Class ENUM('Economy', 'Business', 'First') NOT NULL,
    BookingStatus ENUM('Confirmed', 'Cancelled') NOT NULL,
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID),
    FOREIGN KEY (PassengerID) REFERENCES Passengers(PassengerID)
);

-- 5. Employees Table
CREATE TABLE Employees (
    EmployeeID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Role VARCHAR(50) NOT NULL,
    Department VARCHAR(50) NOT NULL,
    ContactInfo VARCHAR(255),
    Salary DECIMAL(10, 2) NOT NULL
);

-- 6. Terminals Table
CREATE TABLE Terminals (
    TerminalID INT PRIMARY KEY,
    Name VARCHAR(50) NOT NULL,
    Capacity INT NOT NULL,
    Status ENUM('Operational', 'Under Maintenance') NOT NULL
);

-- 7. Gates Table
CREATE TABLE Gates (
    GateID INT PRIMARY KEY,
    TerminalID INT,
    GateNumber VARCHAR(10) NOT NULL,
    Status ENUM('Available', 'Occupied', 'Maintenance') NOT NULL,
    FOREIGN KEY (TerminalID) REFERENCES Terminals(TerminalID)
);

-- 8. Runways Table
CREATE TABLE Runways (
    RunwayID INT PRIMARY KEY,
    RunwayNumber VARCHAR(10) NOT NULL,
    Status ENUM('Available', 'Occupied', 'Maintenance') NOT NULL
);

-- 9. MaintenanceSchedule Table
CREATE TABLE MaintenanceSchedule (
    MaintenanceID INT PRIMARY KEY,
    Type ENUM('Runway', 'Aircraft', 'Gate') NOT NULL,
    Description TEXT,
    ScheduledDate DATE NOT NULL,
    EmployeeID INT,
    FOREIGN KEY (EmployeeID) REFERENCES Employees(EmployeeID)
);

-- 10. Baggage Table
CREATE TABLE Baggage (
    BaggageID INT PRIMARY KEY,
    PassengerID INT,
    FlightID INT,
    Status ENUM('Checked In', 'In Transit', 'Delivered') NOT NULL,
    FOREIGN KEY (PassengerID) REFERENCES Passengers(PassengerID),
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID)
);

-- 11. SecurityCheckpoints Table
CREATE TABLE SecurityCheckpoints (
    CheckpointID INT PRIMARY KEY,
    Location VARCHAR(50) NOT NULL,
    GateID INT,
    Status ENUM('Active', 'Inactive') NOT NULL,
    FOREIGN KEY (GateID) REFERENCES Gates(GateID)
);

-- 12. FuelStations Table
CREATE TABLE FuelStations (
    FuelStationID INT PRIMARY KEY,
    Location VARCHAR(50) NOT NULL,
    Capacity DECIMAL(10, 2) NOT NULL
);

-- 13. WeatherInfo Table
CREATE TABLE WeatherInfo (
    WeatherID INT PRIMARY KEY,
    Date DATE NOT NULL,
    Time TIME NOT NULL,
    Conditions ENUM('Sunny', 'Rainy', 'Stormy', 'Cloudy') NOT NULL
);

-- 14. Immigration Table
CREATE TABLE Immigration (
    ImmigrationID INT PRIMARY KEY,
    PassengerID INT,
    FlightID INT,
    Status ENUM('Approved', 'Pending') NOT NULL,
    FOREIGN KEY (PassengerID) REFERENCES Passengers(PassengerID),
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID)
);

-- 15. AirlineStaff Table
CREATE TABLE AirlineStaff (
    StaffID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Role VARCHAR(50) NOT NULL,
    AirlineID INT,
    FOREIGN KEY (AirlineID) REFERENCES Airlines(AirlineID)
);

-- 16. VIPLounge Table
CREATE TABLE VIPLounge (
    LoungeID INT PRIMARY KEY,
    Name VARCHAR(50) NOT NULL,
    Capacity INT NOT NULL,
    Status ENUM('Open', 'Closed') NOT NULL
);

-- 17. Cargo Table
CREATE TABLE Cargo (
    CargoID INT PRIMARY KEY,
    Weight DECIMAL(10, 2) NOT NULL,
    FlightID INT,
    Status ENUM('Loaded', 'Unloaded', 'In Transit') NOT NULL,
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID)
);

-- 18. TaxiService Table
CREATE TABLE TaxiService (
    TaxiID INT PRIMARY KEY,
    DriverName VARCHAR(100) NOT NULL,
    LicenseNo VARCHAR(50) NOT NULL
);

-- 19. LostAndFound Table
CREATE TABLE LostAndFound (
    ItemID INT PRIMARY KEY,
    Description TEXT NOT NULL,
    FoundDate DATE NOT NULL
);

-- 20. DutyFreeShop Table
CREATE TABLE DutyFreeShop (
    PurchaseID INT PRIMARY KEY,
    PassengerID INT,
    ItemName VARCHAR(50) NOT NULL,
    Price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (PassengerID) REFERENCES Passengers(PassengerID)
);

-- 21. EmergencyContacts Table
CREATE TABLE EmergencyContacts (
    ContactID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Relation VARCHAR(50) NOT NULL,
    Phone VARCHAR(20) NOT NULL,
    PassengerID INT,
    FOREIGN KEY (PassengerID) REFERENCES Passengers(PassengerID)
);

-- 22. ParkingLot Table
CREATE TABLE ParkingLot (
    ParkingID INT PRIMARY KEY,
    Location VARCHAR(50) NOT NULL,
    Capacity INT NOT NULL,
    Status ENUM('Available', 'Full') NOT NULL
);

-- 23. HotelReservations Table
CREATE TABLE HotelReservations (
    ReservationID INT PRIMARY KEY,
    HotelName VARCHAR(100) NOT NULL,
    CheckInDate DATE NOT NULL,
    CheckOutDate DATE NOT NULL,
    PassengerID INT,
    FOREIGN KEY (PassengerID) REFERENCES Passengers(PassengerID)
);

-- 24. FlightCrewSchedule Table
CREATE TABLE FlightCrewSchedule (
    ScheduleID INT PRIMARY KEY,
    CrewMemberID INT NOT NULL,
    FlightID INT,
    Role ENUM('Pilot', 'Co-Pilot', 'Cabin Crew') NOT NULL,
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID)
);

-- 25. EmergencyProtocol Table
CREATE TABLE EmergencyProtocol (
    ProtocolID INT PRIMARY KEY,
    Type ENUM('Fire', 'Medical', 'Security') NOT NULL,
    Description TEXT NOT NULL
);
