package airport.entrance.management;

import java.util.List;
import java.util.Scanner;

public class AddNewID {
    // The scanner is passed in rather than created here. A second Scanner over
    // System.in would buffer input of its own and swallow what the caller's
    // scanner had already read ahead.
    public void execute(List<Person> persons, Scanner scanner) {
        String name = Console.readLine(scanner, "Enter Name: ");
        if (name.isEmpty()) {
            System.out.println("Name cannot be empty. Nothing was added.");
            return;
        }

        int id = Console.readInt(scanner, "Enter ID: ");

        for (Person person : persons) {
            if (person.getId() == id) {
                System.out.println("ID " + id + " already belongs to " + person.getName()
                        + ". Nothing was added.");
                return;
            }
        }

        String num = Console.readLine(scanner, "Enter Contact Number: ");

        persons.add(new Person(name, id, num));
        System.out.println("ID added successfully!");
    }
}
