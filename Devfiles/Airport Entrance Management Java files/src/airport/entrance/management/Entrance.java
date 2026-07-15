package airport.entrance.management;

import java.util.ArrayList;
import java.util.List;
import java.util.Scanner;

public class Entrance {
    private List<Person> persons = new ArrayList<>();

    public void start() {
        // One Scanner for the whole program, handed to whoever needs input.
        // Each class building its own over System.in gave every instance a private
        // buffer, and whichever read first swallowed input the others expected.
        //
        // It is deliberately never closed: closing a Scanner closes System.in with
        // it, and System.in cannot be reopened.
        Scanner scanner = new Scanner(System.in);

        int choice;
        do {
            System.out.println();
            System.out.println("Gate Pass System Menu:");
            System.out.println("1. Add a new ID");
            System.out.println("2. Access Gate");
            System.out.println("3. Book a Ticket");
            System.out.println("4. View Entries");
            System.out.println("0. Exit");
            choice = Console.readInt(scanner, "Enter your choice: ");

            switch (choice) {
                case 1:
                    new AddNewID().execute(persons, scanner);
                    break;
                case 2:
                    new AccessGate().execute(persons, scanner);
                    break;
                case 3:
                    bookTicket(scanner);
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
    }

    // Method for booking a ticket
    private void bookTicket(Scanner scanner) {
        String name = Console.readLine(scanner, "Enter Passenger Name: ");
        String nationalId = Console.readLine(scanner, "Enter National ID Card Number: ");
        String destination = Console.readLine(scanner, "Enter Destination: ");
        String date = Console.readLine(scanner, "Enter Date of Travel: ");

        TicketBooking ticket = new TicketBooking(name, nationalId, destination, date);

        System.out.println();
        System.out.println("Ticket Information:");
        ticket.displayTicketInfo();
    }
}
