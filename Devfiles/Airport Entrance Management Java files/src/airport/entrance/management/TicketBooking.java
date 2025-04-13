package airport.entrance.management;

public class TicketBooking {
    private String name;
    private String nationalId;
    private String destination;
    private String date;

    public TicketBooking(String name, String nationalId, String destination, String date) {
        this.name = name;
        this.nationalId = nationalId;
        this.destination = destination;
        this.date = date;
    }

    public void displayTicketInfo() {
        System.out.println("Passenger Name: " + name);
        System.out.println("National ID: " + nationalId);
        System.out.println("Destination: " + destination);
        System.out.println("Date of Travel: " + date);
    }
}
