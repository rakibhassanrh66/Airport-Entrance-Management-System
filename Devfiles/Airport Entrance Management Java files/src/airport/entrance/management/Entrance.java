package airport.entrance.management;

import java.util.ArrayList;
import java.util.List;
import java.util.Scanner;

public class Entrance {
    private List<Person> persons = new ArrayList<>();

    public void start() {
        Scanner scanner = new Scanner(System.in);

        int choice;
        do {
            System.out.println("Gate Pass System Menu:");
            System.out.println("1. Add a new ID");
            System.out.println("2. Access Gate");
            System.out.println("3. Book a Ticket");
            System.out.println("4. View Entries");
            System.out.println("0. Exit");
            System.out.print("Enter your choice: ");
            choice = scanner.nextInt();
            scanner.nextLine(); // Consume newline

            switch (choice) {
                case 1:
                    new AddNewID().execute(persons);
                    break;
                case 2:
                    new AccessGate().execute(persons);
                    break;
                case 3:
                    bookTicket(scanner); // Call the ticket booking method and pass the scanner
                    break;
                case 4:
                    new ViewEntries().execute(persons);
                    break;
                case 0:
                    System.out.println("Exiting Gate Pass System.");
                    break;
                default:
                    System.out.println("Invalid choice. Please try again.");
            }
        } while (choice != 0);
        scanner.close(); // Close the scanner when finished
    }

    // Method for booking a ticket
    private void bookTicket(Scanner scanner) {
        System.out.print("Enter Passenger Name: ");
        String name = scanner.nextLine();

        System.out.print("Enter National ID Card Number: ");
        String nationalId = scanner.nextLine();

        System.out.print("Enter Destination: ");
        String destination = scanner.nextLine();

        System.out.print("Enter Date of Travel: ");
        String date = scanner.nextLine();

        TicketBooking ticket = new TicketBooking(name, nationalId, destination, date);

        System.out.println("\nTicket Information:");
        ticket.displayTicketInfo();
    }
}
